"""B06 — properties of the confidence model.

Confidence decides whether police are called, so the arithmetic has to hold up under
adversarial input, not just typical input. These properties are the guarantees the
design claims:

    ORDER INDEPENDENCE  -- same reports, any order, identical score
    BOUNDED             -- always in [0, 1], with no clamping anywhere
    MONOTONIC           -- more evidence never lowers confidence
    SATURATING          -- the tenth report adds less than the second
    DECAYING            -- an older report contributes less than a fresh one

The last one is what lets stale incidents leave the map on their own. Systems that rely
on users tidying up after themselves fill with rubbish.
"""

from __future__ import annotations

import datetime as dt
import random
import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.confidence import (
    DEFAULT_EVIDENCE_STRENGTH,
    DEFAULT_HALF_LIFE_MINUTES,
    THRESHOLD_CORROBORATED,
    THRESHOLD_VERIFIED,
    combine,
    decay_factor,
    report_weight,
    score,
    status_for,
)

NOW = dt.datetime(2026, 8, 13, 6, 40, tzinfo=dt.timezone.utc)

reputations = st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False)
ages = st.floats(0.0, 600.0, allow_nan=False, allow_infinity=False)
weights = st.floats(0.0, 0.999, allow_nan=False, allow_infinity=False)


@st.composite
def report_tuples(draw, count: int | None = None):
    n = count if count is not None else draw(st.integers(0, 20))
    out = []
    for _ in range(n):
        out.append((
            uuid.UUID(int=draw(st.integers(0, 2**128 - 1))),
            draw(reputations),
            NOW - dt.timedelta(minutes=draw(st.integers(0, 300))),
        ))
    ids = [r[0] for r in out]
    return out if len(set(ids)) == len(ids) else out[:0]


# =============================================================================
# ORDER INDEPENDENCE
# =============================================================================


@given(reports=report_tuples(), seed=st.integers(0, 10_000))
def test_order_never_changes_the_score(reports, seed) -> None:
    """Same guarantee as clustering, same reason: arrival order over a mobile network
    is effectively random, so it must not affect what anyone sees."""
    shuffled = list(reports)
    random.Random(seed).shuffle(shuffled)

    a = score(reports, now=NOW)
    b = score(shuffled, now=NOW)

    assert a.confidence == b.confidence
    assert [e.report_id for e in a.evidence] == [e.report_id for e in b.evidence]
    assert [e.weight for e in a.evidence] == [e.weight for e in b.evidence]


@given(ws=st.lists(weights, max_size=20))
def test_combine_is_order_independent(ws) -> None:
    """Asserts equality, not approximate equality. Floating-point multiplication is not
    associative, so a naive implementation fails this — which is the point."""
    shuffled = list(ws)
    random.Random(4).shuffle(shuffled)
    assert combine(ws) == combine(shuffled)


# =============================================================================
# BOUNDED
# =============================================================================


@given(ws=st.lists(weights, max_size=50))
def test_confidence_stays_within_zero_and_one(ws) -> None:
    """No clamping anywhere in the code — the formula cannot leave the range. A model
    needing min/max guards to stay legal is a model that does not mean anything."""
    assert 0.0 <= combine(ws) <= 1.0


@given(reports=report_tuples())
def test_scored_confidence_is_bounded(reports) -> None:
    assert 0.0 <= score(reports, now=NOW).confidence <= 1.0


@given(reputation=reputations, age=ages)
def test_single_report_weight_is_bounded(reputation, age) -> None:
    w = report_weight(reputation, age)
    assert 0.0 <= w <= DEFAULT_EVIDENCE_STRENGTH


def test_no_single_report_can_verify_an_incident_alone() -> None:
    """Corroboration is the entire point. If one report could reach the escalation
    threshold, a single fabricated report could summon police."""
    assert report_weight(reputation=1.0, age_minutes=0.0) < THRESHOLD_VERIFIED


# =============================================================================
# MONOTONIC AND SATURATING
# =============================================================================


@given(ws=st.lists(weights, max_size=20), extra=weights)
def test_more_evidence_never_lowers_confidence(ws, extra) -> None:
    assert combine([*ws, extra]) >= combine(ws) - 1e-12


@given(w=st.floats(0.01, 0.5, allow_nan=False, allow_infinity=False))
def test_each_further_report_adds_less_than_the_last(w) -> None:
    """Saturation. The first independent confirmation changes your mind; the fiftieth
    does not. Summing weights would treat them as equal and exceed 1."""
    first = combine([w]) - combine([])
    second = combine([w, w]) - combine([w])
    third = combine([w, w, w]) - combine([w, w])
    assert first > second > third


def test_empty_evidence_is_zero_confidence() -> None:
    assert combine([]) == 0.0
    assert score([], now=NOW).confidence == 0.0


# =============================================================================
# DECAY
# =============================================================================


@given(reputation=st.floats(0.01, 1.0, allow_nan=False, allow_infinity=False))
def test_a_fresh_report_outweighs_an_old_one(reputation) -> None:
    assert report_weight(reputation, 0.0) > report_weight(reputation, 120.0)


def test_one_half_life_halves_the_contribution() -> None:
    assert decay_factor(DEFAULT_HALF_LIFE_MINUTES) == pytest.approx(0.5)
    assert decay_factor(DEFAULT_HALF_LIFE_MINUTES * 2) == pytest.approx(0.25)


def test_a_fresh_report_is_undiminished() -> None:
    assert decay_factor(0.0) == 1.0


def test_clock_drift_into_the_future_is_treated_as_fresh() -> None:
    """Phone clocks drift. Intake already rejects anything meaningfully ahead, so a few
    seconds should not produce a weight above 1."""
    assert decay_factor(-5.0) == 1.0


@given(a=ages, b=ages)
def test_decay_never_increases_with_age(a, b) -> None:
    lo, hi = min(a, b), max(a, b)
    assert decay_factor(lo) >= decay_factor(hi)


def test_a_day_old_report_counts_for_almost_nothing() -> None:
    """This is what makes incidents clear themselves. Nobody has to press a button, and
    systems that depend on users tidying up fill with rubbish."""
    assert decay_factor(24 * 60) < 1e-9


def test_zero_half_life_is_an_error_not_a_division_by_zero() -> None:
    with pytest.raises(ValueError):
        decay_factor(10.0, half_life_minutes=0)


# =============================================================================
# CALIBRATION — does the model behave sensibly for real situations?
# =============================================================================


def _n_fresh(n: int, reputation: float = 0.5):
    return [(uuid.UUID(int=i + 1), reputation, NOW) for i in range(n)]


def test_a_lone_anonymous_report_does_not_alert_anybody() -> None:
    result = score(_n_fresh(1), now=NOW)
    assert result.confidence < THRESHOLD_CORROBORATED
    assert status_for(result.confidence) == "reported"


def test_a_handful_of_ordinary_reports_reaches_the_police() -> None:
    """Five independent reports of average reputation should cross the threshold."""
    assert score(_n_fresh(5), now=NOW).confidence >= THRESHOLD_VERIFIED


def test_trusted_reporters_escalate_faster() -> None:
    """Three reporters with a strong record are worth more than three unknowns —
    that is the entire purpose of tracking reputation."""
    trusted = score(_n_fresh(3, reputation=0.95), now=NOW).confidence
    unknown = score(_n_fresh(3, reputation=0.5), now=NOW).confidence
    assert trusted > unknown


def test_a_discredited_reporter_barely_moves_the_needle() -> None:
    """The defence against someone sitting at home inventing road closures."""
    assert score(_n_fresh(3, reputation=0.02), now=NOW).confidence < THRESHOLD_CORROBORATED


def test_an_unconfirmed_incident_fades_by_itself() -> None:
    stale = [(uuid.UUID(int=1), 0.5, NOW - dt.timedelta(hours=6))]
    assert score(stale, now=NOW).is_stale


def test_the_nineteen_report_crash_is_firmly_verified() -> None:
    """The scenario from the design documents."""
    reports = [
        (uuid.UUID(int=i + 1), 0.5, NOW - dt.timedelta(minutes=i % 5))
        for i in range(19)
    ]
    result = score(reports, now=NOW)
    assert result.is_verified
    assert result.confidence > 0.95


def test_evidence_is_returned_so_the_score_can_be_explained() -> None:
    """An officer must be able to see why confidence is what it is. A number they
    cannot interrogate is a number they will learn to ignore."""
    result = score(_n_fresh(3), now=NOW)
    assert len(result.evidence) == 3
    assert all(e.weight > 0 for e in result.evidence)
    assert [e.report_id for e in result.evidence] == sorted(e.report_id for e in result.evidence)


# =============================================================================
# THRESHOLDS
# =============================================================================


@given(c=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False))
def test_status_is_one_of_three_confidence_derived_states(c) -> None:
    """`assigned` and `resolved` require a human decision and must never be reachable
    by arithmetic alone."""
    assert status_for(c) in {"reported", "corroborated", "verified"}


def test_thresholds_are_ordered() -> None:
    assert 0 < THRESHOLD_CORROBORATED < THRESHOLD_VERIFIED < 1


@pytest.mark.parametrize(
    "confidence,expected",
    [(0.0, "reported"), (0.34, "reported"), (0.35, "corroborated"),
     (0.69, "corroborated"), (0.70, "verified"), (1.0, "verified")],
)
def test_threshold_boundaries(confidence: float, expected: str) -> None:
    assert status_for(confidence) == expected


def test_invalid_reputation_is_rejected() -> None:
    with pytest.raises(ValueError):
        report_weight(reputation=1.5, age_minutes=0)
    with pytest.raises(ValueError):
        report_weight(reputation=-0.1, age_minutes=0)
