"""Deciding which reports describe the same real-world event.

Nineteen people report a jackknifed truck on the Spintex Road in four minutes. Nobody
tells the system it is one crash. It has to work that out from where and when each
report came in.

This module is **pure**: no database, no clock, no randomness. Give it the same reports
and it returns the same answer, every time, forever. That is what makes it possible to
generate thousands of test cases in seconds, which in turn is what lets us *prove* the
order-independence property rather than assert it.


THE PROPERTY THAT MUST NEVER BREAK
----------------------------------
    The order reports arrive in must not change the result.

Over a mobile network, arrival order is effectively random — one reporter is on 4G,
another on failing 3G, and their reports overtake each other in transit. If order
changed the answer, two commuters could open the app and see genuinely different maps
of the same road, and neither would be wrong.


WHY THE OBVIOUS APPROACH FAILS
------------------------------
The natural first attempt is incremental: for each arriving report, look for a nearby
incident, join it if there is one, otherwise start a new incident.

That is order-dependent, and here is the counter-example. Three reports in a line,
200 m apart, with a 300 m radius::

    A -------- B -------- C
       200 m      200 m
    (A to C is 400 m)

Arriving A, B, C: A starts an incident. B is 200 m from A, joins. C is 200 m from B,
joins. One incident.

Arriving A, C, B: A starts one incident. C is 400 m from A, so starts a second. B is
within 300 m of *both* — and whichever it joins, the answer differs from the first
ordering.

The bug is not in the tie-breaking. It is that incremental assignment asks "what
already exists?", and what already exists depends on order.


WHAT WE DO INSTEAD
------------------
Recompute the whole grouping from the full set of reports, as a graph problem.

Draw an edge between two reports when they are the same type, within the distance
limit, and within the time window. Then the incidents are the **connected components**
of that graph.

This is order-independent by construction, and provably so: the connected components of
a graph do not depend on the order the edges were added. There is no "already exists" to
depend on. Each report reaches its component through some chain of links, and whether a
chain exists is a fact about the graph, not about arrival times.

This is single-linkage agglomerative clustering, computed by union-find.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Iterable, Sequence

from app.geo import haversine_metres

DEFAULT_RADIUS_METRES = 300
DEFAULT_WINDOW_MINUTES = 30


@dataclass(frozen=True)
class ReportPoint:
    """The only facts about a report that clustering needs.

    Deliberately not the database model. Keeping this module free of SQLAlchemy is what
    lets Hypothesis build ten thousand of them a second.
    """

    id: uuid.UUID
    incident_type: str
    latitude: float
    longitude: float
    occurred_at: dt.datetime


@dataclass(frozen=True)
class Cluster:
    """One real-world event, as inferred from the reports describing it."""

    incident_type: str
    members: tuple[ReportPoint, ...]      # always sorted by id
    centroid_latitude: float
    centroid_longitude: float
    first_occurred_at: dt.datetime
    last_occurred_at: dt.datetime

    @property
    def key(self) -> uuid.UUID:
        """A stable identity derived from the contents.

        The smallest member id. Because membership is order-independent and the
        minimum of a set does not depend on iteration order, the same set of reports
        always produces the same key — which is what lets a recomputed cluster be
        matched to the incident row it corresponds to.
        """
        return self.members[0].id

    @property
    def size(self) -> int:
        return len(self.members)


# --- the linking rule ---------------------------------------------------------


def are_linked(
    a: ReportPoint,
    b: ReportPoint,
    radius_metres: float = DEFAULT_RADIUS_METRES,
    window_minutes: float = DEFAULT_WINDOW_MINUTES,
) -> bool:
    """Do these two reports plausibly describe the same event?

    Three conditions, all required:

    1. Same type. A flood and a collision at one junction are two events.
    2. Close in space. Within `radius_metres`.
    3. Close in time. Within `window_minutes`.

    Both space and time are needed. Two crashes at Circle on Monday and Friday share a
    location exactly and are obviously separate; two reports 15 km apart in the same
    minute are equally obviously separate.

    This relation is **symmetric** — are_linked(a, b) == are_linked(b, a) — and that is
    load-bearing. An asymmetric rule would make the graph directed, and the whole
    order-independence argument would collapse.
    """
    if a.incident_type != b.incident_type:
        return False

    gap = abs((a.occurred_at - b.occurred_at).total_seconds())
    if gap > window_minutes * 60:
        return False

    distance = haversine_metres(a.latitude, a.longitude, b.latitude, b.longitude)
    return distance <= radius_metres


# --- union-find ---------------------------------------------------------------


class _DisjointSet:
    """Tracks which things have been merged into which group.

    Two operations: `union(a, b)` says these belong together, `find(a)` says which group
    something is in. Both effectively constant time.

    Path compression and union by size are optimisations only — they change how fast the
    answer is reached, never what it is. The resulting partition is identical either way,
    which matters here because determinism is the whole point.
    """

    def __init__(self, items: Iterable[int]) -> None:
        self._parent = {i: i for i in items}
        self._size = {i: 1 for i in self._parent}

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:      # path compression
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._size[ra] < self._size[rb]:  # union by size
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size[rb]


# --- centroid -----------------------------------------------------------------


def centroid(points: Sequence[ReportPoint]) -> tuple[float, float]:
    """Mean position of a cluster.

    THE SUBTLE BIT. Floating-point addition is **not associative**:

        (0.1 + 0.2) + 0.3  !=  0.1 + (0.2 + 0.3)

    Both are 0.6 to any sane precision, but they differ in the last bit. So summing the
    same coordinates in a different order can produce a centroid that differs by about
    1e-16 degrees — a few nanometres on the ground, and utterly meaningless.

    It is still a broken promise. The property test asserts results are *identical*, not
    *nearly identical*, and it would catch this. Weakening the test to a tolerance would
    have hidden a real class of bug behind an approximate assertion.

    So we sort by id before summing. The addition order becomes a fact about the data
    rather than about arrival sequence, and the result is bit-for-bit reproducible.

    (Averaging raw degrees is wrong near the poles and across the date line. Ghana is
    near the equator and nowhere near ±180°, so it is correct here. Recorded as a
    limitation rather than left as an assumption.)
    """
    if not points:
        raise ValueError("centroid of an empty cluster is undefined")

    ordered = sorted(points, key=lambda p: p.id)
    n = len(ordered)
    return (
        sum(p.latitude for p in ordered) / n,
        sum(p.longitude for p in ordered) / n,
    )


# --- the entry point ----------------------------------------------------------


def cluster_reports(
    reports: Sequence[ReportPoint],
    radius_metres: float = DEFAULT_RADIUS_METRES,
    window_minutes: float = DEFAULT_WINDOW_MINUTES,
) -> list[Cluster]:
    """Group reports into the events they describe.

    Order-independent: the returned list is identical for any permutation of the input.

    Two things make that true. The grouping is the connected components of a symmetric
    graph, which do not depend on edge insertion order. And every output is then sorted
    by a stable key derived from the data — members by id, clusters by their smallest
    member id — so even the sequence of the answer is fixed.
    """
    if not reports:
        return []

    # Sort first. Everything downstream then works in a canonical order regardless of
    # how the caller supplied the reports.
    ordered = sorted(reports, key=lambda r: r.id)
    n = len(ordered)

    # Only same-type reports can ever link, so compare within type buckets. Purely a
    # speed optimisation — the result is unchanged, since are_linked would reject a
    # cross-type pair anyway.
    by_type: dict[str, list[int]] = {}
    for i, r in enumerate(ordered):
        by_type.setdefault(r.incident_type, []).append(i)

    ds = _DisjointSet(range(n))
    for indices in by_type.values():
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                ia, ib = indices[a], indices[b]
                if are_linked(ordered[ia], ordered[ib], radius_metres, window_minutes):
                    ds.union(ia, ib)

    groups: dict[int, list[ReportPoint]] = {}
    for i in range(n):
        groups.setdefault(ds.find(i), []).append(ordered[i])

    clusters: list[Cluster] = []
    for members in groups.values():
        members.sort(key=lambda p: p.id)
        lat, lon = centroid(members)
        times = [m.occurred_at for m in members]
        clusters.append(
            Cluster(
                incident_type=members[0].incident_type,
                members=tuple(members),
                centroid_latitude=lat,
                centroid_longitude=lon,
                first_occurred_at=min(times),
                last_occurred_at=max(times),
            )
        )

    clusters.sort(key=lambda c: c.key)
    return clusters
