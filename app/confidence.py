"""How believable is this incident?

Clustering answers "which reports describe the same event". This module answers the
harder question: **should anyone act on it?**

That matters because the system decides whether police are called. It cannot simply
believe whatever it is told — some reports are mistaken, and some are fabricated by
someone who wants a rival's route flagged as blocked.

Like `clustering.py`, this module is **pure**: no database, no clock, no randomness. The
current time is passed in rather than read, so the same inputs always give the same
answer and every property can be tested exhaustively.


THE MODEL
---------
Each report contributes evidence:

    weight = reputation x decay(age) x evidence_strength

- **reputation** — how often this person's past reports proved true. New accounts start
  at 0.5: neither trusted nor distrusted.
- **decay(age)** — halves every `half_life_minutes`. A flood reported four hours ago
  says very little about that road now.
- **evidence_strength** — a ceiling on how much any single report can ever contribute.
  Without it one trusted reporter could verify an incident alone, which defeats the
  purpose of corroboration.

Those weights are then combined with **noisy-OR**:

    confidence = 1 - product(1 - weight_i)

Read it as probability. If report i is independently right with probability w_i, then
the chance they are *all* wrong is the product of (1 - w_i), so the chance at least one
is right is one minus that.

Three properties fall out of that formula for free, and each is one we actually need:

    bounded    -- always between 0 and 1, no clamping required
    monotonic  -- more evidence never lowers confidence
    saturating -- the tenth report adds less than the second

And critically: **multiplication is commutative, so the result does not depend on the
order reports arrive in.** Same guarantee as clustering, same reason.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Sequence

# --- tuning knobs -------------------------------------------------------------
# All three are read from environment variables in production so they can be
# adjusted without a redeploy. They are guesses fitted to no data — see TD-04.

DEFAULT_HALF_LIFE_MINUTES = 45.0

# The ceiling on a single report's contribution. At 0.45, a lone reporter of average
# reputation (0.5) yields about 0.22 — visible on the map, nowhere near the escalation
# threshold. Roughly five such reports are needed to verify, or three from consistently
# reliable reporters.
DEFAULT_EVIDENCE_STRENGTH = 0.45

# How much more a report carrying a voice note or photograph counts. Deliberately
# modest: recorded evidence is harder to fabricate than a tapped coordinate, but it is
# still not proof, and the bonus is capped so an attachment can never on its own push a
# report past the escalation threshold.
EVIDENCE_BONUS = 1.25

# Where an incident moves from "someone said something" to "tell the police".
THRESHOLD_CORROBORATED = 0.35
THRESHOLD_VERIFIED = 0.70

# Below this an incident has faded and should leave the map without anyone closing it.
THRESHOLD_STALE = 0.05


@dataclass(frozen=True)
class Evidence:
    """One report's contribution, kept separately so a score can be explained."""

    report_id: uuid.UUID
    reporter_reputation: float
    age_minutes: float
    weight: float


@dataclass(frozen=True)
class ConfidenceResult:
    confidence: float
    evidence: tuple[Evidence, ...]     # sorted by report id

    @property
    def is_verified(self) -> bool:
        return self.confidence >= THRESHOLD_VERIFIED

    @property
    def is_corroborated(self) -> bool:
        return self.confidence >= THRESHOLD_CORROBORATED

    @property
    def is_stale(self) -> bool:
        return self.confidence < THRESHOLD_STALE


def decay_factor(age_minutes: float, half_life_minutes: float = DEFAULT_HALF_LIFE_MINUTES) -> float:
    """How much a report still counts, given its age.

    Exponential half-life: 1.0 when fresh, 0.5 after one half-life, 0.25 after two.
    Chosen over a linear fade because linear needs an arbitrary cut-off point where
    evidence vanishes in a single step — and an incident that disappears at exactly
    90 minutes is a cliff no reporter would recognise.

    A negative age means the report is slightly in the future, which happens with
    ordinary phone clock drift. Treated as fresh rather than as an error; intake has
    already rejected anything meaningfully ahead of the server clock.
    """
    if half_life_minutes <= 0:
        raise ValueError("half_life_minutes must be positive")
    if age_minutes <= 0:
        return 1.0
    return 0.5 ** (age_minutes / half_life_minutes)


def report_weight(
    reputation: float,
    age_minutes: float,
    half_life_minutes: float = DEFAULT_HALF_LIFE_MINUTES,
    evidence_strength: float = DEFAULT_EVIDENCE_STRENGTH,
    recorded_evidence: bool = False,
) -> float:
    """Evidence contributed by one report, in the range [0, 1).

    `recorded_evidence` is set when the report carries a voice note or photograph. Such
    a report counts for more, because a recording is far harder to fabricate from an
    armchair than a tapped coordinate: it demonstrates the reporter was somewhere with
    something to describe.

    The bonus is modest and **capped**, so an attachment can never on its own carry a
    report past the escalation threshold. Corroboration still does that. A larger bonus
    would turn "attach any audio file" into a way of buying credibility.
    """
    if not 0.0 <= reputation <= 1.0:
        raise ValueError(f"reputation must be within [0, 1], got {reputation}")
    if not 0.0 <= evidence_strength <= 1.0:
        raise ValueError(f"evidence_strength must be within [0, 1], got {evidence_strength}")

    weight = reputation * decay_factor(age_minutes, half_life_minutes) * evidence_strength
    if recorded_evidence:
        weight *= EVIDENCE_BONUS

    # Never past the ceiling a single report is allowed to reach.
    return min(weight, evidence_strength)


def combine(weights: Sequence[float]) -> float:
    """Noisy-OR: 1 - product(1 - w).

    Summing weights would be wrong twice over — it can exceed 1, and it treats the
    hundredth report as worth as much as the second. Noisy-OR saturates, which matches
    how corroboration actually behaves: the first independent confirmation changes your
    mind, the fiftieth does not.

    The weights are sorted before multiplying. Floating-point multiplication, like
    addition, is not associative, so a different order could change the last bit of the
    result. The property tests assert *identical* answers rather than approximately
    equal ones, so that difference would show up — and weakening the assertion to a
    tolerance would let arrival order matter a little, which is precisely what must not
    happen. Same reasoning as `clustering.centroid`.
    """
    remaining = 1.0
    for w in sorted(weights):
        remaining *= (1.0 - w)
    return 1.0 - remaining


def score(
    reports: Sequence[tuple[uuid.UUID, float, dt.datetime]],
    now: dt.datetime,
    half_life_minutes: float = DEFAULT_HALF_LIFE_MINUTES,
    evidence_strength: float = DEFAULT_EVIDENCE_STRENGTH,
    with_recorded_evidence: set[uuid.UUID] | None = None,
) -> ConfidenceResult:
    """Score one incident from its reports.

    Each entry is (report_id, reporter_reputation, occurred_at).

    The per-report evidence is returned alongside the total, not discarded. That is what
    lets the interface show an officer *why* confidence is 0.91 — which reporters, how
    reliable, how recent — rather than presenting a number and asking for trust. An
    unexplainable score is one an officer will learn to ignore.
    """
    if not reports:
        return ConfidenceResult(confidence=0.0, evidence=())

    recorded = with_recorded_evidence or set()

    evidence: list[Evidence] = []
    for report_id, reputation, occurred_at in sorted(reports, key=lambda r: r[0]):
        age = (now - occurred_at).total_seconds() / 60.0
        evidence.append(
            Evidence(
                report_id=report_id,
                reporter_reputation=reputation,
                age_minutes=age,
                weight=report_weight(
                    reputation,
                    age,
                    half_life_minutes,
                    evidence_strength,
                    recorded_evidence=report_id in recorded,
                ),
            )
        )

    return ConfidenceResult(
        confidence=combine([e.weight for e in evidence]),
        evidence=tuple(evidence),
    )


def status_for(confidence: float) -> str:
    """Map a score onto the lifecycle state an incident should be in.

    Only the states confidence alone can justify. `assigned` and `resolved` require a
    human decision and are never reached by arithmetic — see the state machine at B08.
    """
    if confidence >= THRESHOLD_VERIFIED:
        return "verified"
    if confidence >= THRESHOLD_CORROBORATED:
        return "corroborated"
    return "reported"
