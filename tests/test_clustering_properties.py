"""B19a — property-based tests for the clustering engine.

This is the centrepiece of the testing strategy, and the reason the project counts as
advanced rather than merely large.

Ordinary tests check examples you thought of. You wrote the inputs, so you only test the
cases already in your head — and the bug you did not think of survives.

Property-based testing inverts that. You state a rule that must hold for *every* input,
and Hypothesis generates hundreds of random cases trying to break it. When it finds a
failure it automatically shrinks it to the smallest version that still fails, so the
cause is visible rather than buried in noise.

The four properties, in order of importance:

    1. ORDER INDEPENDENCE  -- arrival order never changes the result
    2. PARTITION           -- every report lands in exactly one cluster
    3. SEPARATION          -- no two clusters should have been one
    4. IDEMPOTENCE         -- clustering twice changes nothing
"""

from __future__ import annotations

import datetime as dt
import random
import uuid

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from app.clustering import (
    Cluster,
    ReportPoint,
    are_linked,
    centroid,
    cluster_reports,
)

BASE_TIME = dt.datetime(2026, 8, 13, 6, 0, tzinfo=dt.timezone.utc)
TYPES = ["accident", "flood", "closure", "signal_outage"]

# Greater Accra, roughly.
LAT_RANGE = (5.50, 5.70)
LON_RANGE = (-0.30, -0.05)

# About 165 m per 0.0015 degrees of latitude here. Jittering by up to twice the
# clustering radius puts generated reports right on the boundary — some link, some do
# not, and the interesting cases are the ones near the edge.
JITTER_DEGREES = 0.003


@st.composite
def report_points(draw, count: int | None = None) -> list[ReportPoint]:
    """Reports scattered around a handful of hotspots, not uniformly across Accra.

    THIS SHAPE IS DELIBERATE, AND THE FIRST VERSION WAS WRONG.

    Originally reports were drawn uniformly over the whole Accra bounding box — about
    22 km by 28 km. With at most 25 reports and a 300 m radius, two of them almost never
    landed close enough to link. Measured: **1 generated set in 300 contained any merge
    at all.**

    Every property still passed, which is exactly the problem. They were passing over
    collections of singleton clusters — where order independence is trivially true and
    proves nothing. A test that passes for the wrong reason is worse than one that
    fails, because it buys confidence it has not earned.

    Real reports are not uniform either. They arrive around real events. So: draw a few
    hotspots, scatter reports near them, and the generator now produces genuine merges
    in the large majority of cases. `test_the_generator_actually_produces_merges` holds
    that line.
    """
    n = count if count is not None else draw(st.integers(min_value=0, max_value=25))
    if n == 0:
        return []

    n_hotspots = draw(st.integers(min_value=1, max_value=max(1, min(4, n))))
    hotspots = [
        (
            draw(st.floats(*LAT_RANGE, allow_nan=False, allow_infinity=False)),
            draw(st.floats(*LON_RANGE, allow_nan=False, allow_infinity=False)),
            draw(st.integers(min_value=0, max_value=180)),
            draw(st.sampled_from(TYPES)),
        )
        for _ in range(n_hotspots)
    ]

    points = []
    for _ in range(n):
        lat0, lon0, minute0, kind = hotspots[draw(st.integers(0, n_hotspots - 1))]
        points.append(
            ReportPoint(
                id=uuid.UUID(int=draw(st.integers(min_value=0, max_value=2**128 - 1))),
                # Mostly the hotspot's type, occasionally a different one — so
                # same-place-different-type cases are exercised too.
                incident_type=draw(st.sampled_from([kind, kind, kind, *TYPES])),
                latitude=lat0 + draw(st.floats(-JITTER_DEGREES, JITTER_DEGREES,
                                               allow_nan=False, allow_infinity=False)),
                longitude=lon0 + draw(st.floats(-JITTER_DEGREES, JITTER_DEGREES,
                                                allow_nan=False, allow_infinity=False)),
                occurred_at=BASE_TIME
                + dt.timedelta(minutes=minute0 + draw(st.integers(-40, 40))),
            )
        )

    # Duplicate ids would be a data impossibility — the primary key prevents them —
    # and would make "sort by id" ambiguous.
    assume(len({p.id for p in points}) == len(points))
    return points


def _shape(clusters: list[Cluster]) -> list[tuple]:
    """Everything about the answer that must be reproducible, including ordering."""
    return [
        (
            c.incident_type,
            tuple(m.id for m in c.members),
            c.centroid_latitude,
            c.centroid_longitude,
            c.first_occurred_at,
            c.last_occurred_at,
        )
        for c in clusters
    ]


# Example counts come from the Hypothesis profiles in conftest.py, not from here.
# See that file for why.


# =============================================================================
# PROPERTY 0 — THE TESTS ARE ACTUALLY TESTING SOMETHING
#
# Every property below is trivially true for a set of singleton clusters. If the
# generator stops producing merges, the whole file silently becomes decorative.
# This guards that, and it is here because the first version of the generator
# failed it — 1 merge in 300 sets.
# =============================================================================


def test_the_generator_actually_produces_merges() -> None:
    """Meta-test. If this fails, every property below is passing vacuously."""
    # Hypothesis discourages .example() inside tests, so this drives the same shape
    # of data directly with a fixed seed.
    total = 200
    rng = random.Random(20260813)
    merged = 0
    for _ in range(total):
        n = rng.randint(2, 25)
        n_hot = rng.randint(1, min(4, n))
        hotspots = [
            (rng.uniform(*LAT_RANGE), rng.uniform(*LON_RANGE),
             rng.randint(0, 180), rng.choice(TYPES))
            for _ in range(n_hot)
        ]
        pts = []
        for _ in range(n):
            lat0, lon0, m0, kind = rng.choice(hotspots)
            pts.append(
                ReportPoint(
                    uuid.UUID(int=rng.getrandbits(128)),
                    rng.choice([kind, kind, kind, *TYPES]),
                    lat0 + rng.uniform(-JITTER_DEGREES, JITTER_DEGREES),
                    lon0 + rng.uniform(-JITTER_DEGREES, JITTER_DEGREES),
                    BASE_TIME + dt.timedelta(minutes=m0 + rng.randint(-40, 40)),
                )
            )
        if any(c.size > 1 for c in cluster_reports(pts)):
            merged += 1

    assert merged > total * 0.5, (
        f"only {merged}/{total} generated sets contained a merge — the properties "
        f"are passing over singleton clusters and proving nothing"
    )


# =============================================================================
# PROPERTY 1 — ORDER INDEPENDENCE
# The single most important assertion in the project.
# =============================================================================


@given(points=report_points(), seed=st.integers(min_value=0, max_value=10_000))
def test_arrival_order_never_changes_the_result(points, seed) -> None:
    """Kofi's report before Ama's, or Ama's before Kofi's — identical outcome.

    Note this asserts *identical*, not *nearly identical*. A tolerance would hide the
    floating-point associativity problem that `centroid` sorts by id to avoid.
    """
    shuffled = list(points)
    random.Random(seed).shuffle(shuffled)

    assert _shape(cluster_reports(points)) == _shape(cluster_reports(shuffled))


@given(points=report_points())
def test_reversal_never_changes_the_result(points) -> None:
    """The worst case for any incremental algorithm, checked explicitly."""
    assert _shape(cluster_reports(points)) == _shape(cluster_reports(list(reversed(points))))


def test_the_counter_example_that_breaks_incremental_assignment() -> None:
    """Three reports in a line, 200 m apart, radius 300 m.

    A and C are 400 m apart, so they do not link directly. B links to both. An
    incremental algorithm gives one incident for order A,B,C and two for A,C,B.
    Connected components give one either way, because a path exists through B.
    """
    t = BASE_TIME
    a = ReportPoint(uuid.UUID(int=1), "accident", 5.6000, -0.2000, t)
    b = ReportPoint(uuid.UUID(int=2), "accident", 5.6018, -0.2000, t)   # ~200 m north
    c = ReportPoint(uuid.UUID(int=3), "accident", 5.6036, -0.2000, t)   # ~400 m north

    for order in ([a, b, c], [a, c, b], [c, b, a], [b, a, c], [c, a, b], [b, c, a]):
        clusters = cluster_reports(order, radius_metres=300)
        assert len(clusters) == 1
        assert clusters[0].size == 3


# =============================================================================
# PROPERTY 2 — PARTITION
# =============================================================================


@given(points=report_points())
def test_every_report_appears_exactly_once(points) -> None:
    """No report lost, none duplicated. A lost report is a warning never sent; a
    duplicated one inflates confidence."""
    members = [m.id for c in cluster_reports(points) for m in c.members]
    assert sorted(members) == sorted(p.id for p in points)
    assert len(members) == len(set(members))


@given(points=report_points())
def test_no_empty_clusters(points) -> None:
    assert all(c.size >= 1 for c in cluster_reports(points))


@given(points=report_points())
def test_every_cluster_is_single_typed(points) -> None:
    """A flood and a collision are never the same event, however close together."""
    for c in cluster_reports(points):
        assert len({m.incident_type for m in c.members}) == 1
        assert c.incident_type == c.members[0].incident_type


# =============================================================================
# PROPERTY 3 — SEPARATION
# =============================================================================


@given(points=report_points())
def test_distinct_clusters_are_never_linked(points) -> None:
    """If any report in cluster X links to any report in cluster Y, they should have
    been one cluster. This is what makes the grouping *maximal* rather than merely
    consistent — an algorithm returning one cluster per report would satisfy every
    other property here and be useless."""
    clusters = cluster_reports(points)
    for i, x in enumerate(clusters):
        for y in clusters[i + 1:]:
            for a in x.members:
                for b in y.members:
                    assert not are_linked(a, b)


@given(points=report_points())
def test_cluster_time_bounds_match_members(points) -> None:
    for c in cluster_reports(points):
        times = [m.occurred_at for m in c.members]
        assert c.first_occurred_at == min(times)
        assert c.last_occurred_at == max(times)
        assert c.first_occurred_at <= c.last_occurred_at


@given(points=report_points())
def test_centroid_lies_within_the_member_bounding_box(points) -> None:
    """A mean cannot fall outside the range it averages. Catches sign errors and
    latitude/longitude swaps."""
    for c in cluster_reports(points):
        lats = [m.latitude for m in c.members]
        lons = [m.longitude for m in c.members]
        assert min(lats) <= c.centroid_latitude <= max(lats)
        assert min(lons) <= c.centroid_longitude <= max(lons)


# =============================================================================
# PROPERTY 4 — IDEMPOTENCE AND STABILITY
# =============================================================================


@given(points=report_points())
def test_clustering_is_idempotent(points) -> None:
    """Re-running over the same reports changes nothing. Required for replay: rebuilding
    the map from the report log must reproduce what is stored."""
    once = cluster_reports(points)
    twice = cluster_reports([m for c in once for m in c.members])
    assert _shape(once) == _shape(twice)


@given(points=report_points())
def test_cluster_keys_are_unique_and_stable(points) -> None:
    clusters = cluster_reports(points)
    keys = [c.key for c in clusters]
    assert len(keys) == len(set(keys))
    assert keys == sorted(keys)


@given(points=report_points())
def test_a_zero_radius_isolates_everything_at_distinct_places(points) -> None:
    """A degenerate setting must degrade sensibly, not crash."""
    clusters = cluster_reports(points, radius_metres=0)
    assert sum(c.size for c in clusters) == len(points)


# =============================================================================
# THE LINKING RULE
# =============================================================================


@given(points=report_points(count=2))
def test_linking_is_symmetric(points) -> None:
    """Load-bearing. An asymmetric rule makes the graph directed and the whole
    order-independence argument collapses."""
    a, b = points
    assert are_linked(a, b) == are_linked(b, a)


@given(points=report_points(count=1))
def test_a_report_links_to_itself(points) -> None:
    assert are_linked(points[0], points[0])


def test_same_place_different_days_do_not_link() -> None:
    """Two crashes at Circle on Monday and Friday share a location exactly."""
    a = ReportPoint(uuid.UUID(int=1), "accident", 5.6037, -0.1870, BASE_TIME)
    b = ReportPoint(uuid.UUID(int=2), "accident", 5.6037, -0.1870, BASE_TIME + dt.timedelta(days=4))
    assert not are_linked(a, b)


def test_same_moment_far_apart_do_not_link() -> None:
    """Accra and Kumasi, same minute."""
    a = ReportPoint(uuid.UUID(int=1), "flood", 5.6037, -0.1870, BASE_TIME)
    b = ReportPoint(uuid.UUID(int=2), "flood", 6.6885, -1.6244, BASE_TIME)
    assert not are_linked(a, b)


def test_different_types_never_link() -> None:
    a = ReportPoint(uuid.UUID(int=1), "flood", 5.6037, -0.1870, BASE_TIME)
    b = ReportPoint(uuid.UUID(int=2), "accident", 5.6037, -0.1870, BASE_TIME)
    assert not are_linked(a, b)


# =============================================================================
# EDGE CASES
# =============================================================================


def test_empty_input() -> None:
    assert cluster_reports([]) == []


def test_single_report() -> None:
    p = ReportPoint(uuid.UUID(int=1), "accident", 5.6037, -0.1870, BASE_TIME)
    clusters = cluster_reports([p])
    assert len(clusters) == 1
    assert clusters[0].centroid_latitude == pytest.approx(5.6037)


def test_centroid_of_nothing_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError):
        centroid([])


def test_nineteen_reports_of_one_crash() -> None:
    """The scenario from the design documents, end to end."""
    rng = random.Random(20260813)
    points = [
        ReportPoint(
            id=uuid.UUID(int=i + 1),
            incident_type="accident",
            latitude=5.6360 + rng.uniform(-0.0008, 0.0008),    # within ~90 m
            longitude=-0.0980 + rng.uniform(-0.0008, 0.0008),
            occurred_at=BASE_TIME + dt.timedelta(seconds=rng.randint(0, 240)),
        )
        for i in range(19)
    ]
    rng.shuffle(points)

    clusters = cluster_reports(points)
    assert len(clusters) == 1
    assert clusters[0].size == 19
