"""C — the circuit breaker, and clearance notifications.

The breaker takes the current time as an argument rather than reading a clock, so its
entire behaviour — including timeouts and cooling-off periods — is tested without a
single `sleep`. A test suite that waits thirty seconds to check a thirty-second timeout
is a test suite nobody runs.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.circuit_breaker import BreakerState, CircuitBreaker, CircuitOpen
from app.models import IncidentType
from app.services.advisory import ClearanceReason, compose_clearance, _clearance_key
from app.services.staleness import STALE_AFTER_HALF_LIVES, SWEEP_INTERVAL_SECONDS

T0 = dt.datetime(2026, 8, 13, 7, 0, tzinfo=dt.timezone.utc)


def _breaker(threshold: int = 3, reset_seconds: int = 30) -> CircuitBreaker:
    return CircuitBreaker(
        name="test", failure_threshold=threshold,
        reset_after=dt.timedelta(seconds=reset_seconds),
    )


def _fail(b: CircuitBreaker, n: int, at: dt.datetime = T0) -> None:
    for _ in range(n):
        b.record_failure(at)


# =============================================================================
# CLOSED — the normal state
# =============================================================================


def test_a_new_breaker_is_closed() -> None:
    assert _breaker().state(T0) is BreakerState.CLOSED


def test_calls_pass_through_when_closed() -> None:
    _breaker().before_call(T0)      # must not raise


def test_failures_below_the_threshold_do_not_trip() -> None:
    b = _breaker(threshold=3)
    _fail(b, 2)
    assert b.state(T0) is BreakerState.CLOSED


def test_a_success_resets_the_run() -> None:
    """The threshold counts *consecutive* failures. One success means the run ended, so
    scattered failures over a long period never trip it — that is a blip, not an outage."""
    b = _breaker(threshold=3)
    _fail(b, 2)
    b.record_success(T0)
    _fail(b, 2)
    assert b.state(T0) is BreakerState.CLOSED


# =============================================================================
# OPEN — tripped
# =============================================================================


def test_the_threshold_trips_it() -> None:
    b = _breaker(threshold=3)
    _fail(b, 3)
    assert b.state(T0) is BreakerState.OPEN


def test_an_open_breaker_refuses_instantly() -> None:
    """The whole point. Failing here takes microseconds; attempting the call would take
    a thirty-second timeout."""
    b = _breaker(threshold=3)
    _fail(b, 3)
    with pytest.raises(CircuitOpen):
        b.before_call(T0)


def test_the_refusal_says_when_it_will_try_again() -> None:
    b = _breaker(threshold=2, reset_seconds=30)
    _fail(b, 2)
    with pytest.raises(CircuitOpen) as exc:
        b.before_call(T0)
    assert "Retrying at" in str(exc.value)


def test_rejections_are_counted_separately_from_failures() -> None:
    """A rejection is not a failure — nothing was attempted. Conflating them would make
    the failure count meaningless the moment the breaker opens."""
    b = _breaker(threshold=2)
    _fail(b, 2)
    for _ in range(5):
        with pytest.raises(CircuitOpen):
            b.before_call(T0)
    assert b.total_failures == 2
    assert b.total_rejected == 5


def test_it_stays_open_for_the_whole_cooling_off_period() -> None:
    b = _breaker(threshold=2, reset_seconds=30)
    _fail(b, 2)
    assert b.state(T0 + dt.timedelta(seconds=29)) is BreakerState.OPEN


# =============================================================================
# HALF_OPEN — testing the water
# =============================================================================


def test_it_moves_to_half_open_once_the_period_elapses() -> None:
    """Driven by time, not by an event, so it has to be evaluated on read. Nothing
    fires this transition."""
    b = _breaker(threshold=2, reset_seconds=30)
    _fail(b, 2)
    assert b.state(T0 + dt.timedelta(seconds=30)) is BreakerState.HALF_OPEN


def test_a_test_call_is_allowed_when_half_open() -> None:
    b = _breaker(threshold=2, reset_seconds=30)
    _fail(b, 2)
    b.before_call(T0 + dt.timedelta(seconds=31))    # must not raise


def test_a_successful_test_call_closes_it() -> None:
    b = _breaker(threshold=2, reset_seconds=30)
    _fail(b, 2)
    later = T0 + dt.timedelta(seconds=31)
    b.before_call(later)
    b.record_success(later)
    assert b.state(later) is BreakerState.CLOSED


def test_a_failed_test_call_reopens_immediately() -> None:
    """One failure is enough from half-open. The test call was the whole point, and it
    told us the provider is still down — waiting for another four failures would mean
    four more thirty-second timeouts to learn what we already know."""
    b = _breaker(threshold=5, reset_seconds=30)
    _fail(b, 5)
    later = T0 + dt.timedelta(seconds=31)
    b.before_call(later)
    b.record_failure(later)
    assert b.state(later) is BreakerState.OPEN


def test_the_cooling_off_period_restarts_after_a_failed_test() -> None:
    b = _breaker(threshold=2, reset_seconds=30)
    _fail(b, 2)
    t1 = T0 + dt.timedelta(seconds=31)
    b.before_call(t1)
    b.record_failure(t1)
    assert b.state(t1 + dt.timedelta(seconds=29)) is BreakerState.OPEN
    assert b.state(t1 + dt.timedelta(seconds=30)) is BreakerState.HALF_OPEN


# =============================================================================
# PROPERTIES
# =============================================================================


@given(
    failures=st.integers(0, 50),
    threshold=st.integers(1, 10),
)
def test_it_trips_exactly_when_the_threshold_is_reached(failures: int, threshold: int) -> None:
    b = _breaker(threshold=threshold)
    _fail(b, failures)
    expected = BreakerState.OPEN if failures >= threshold else BreakerState.CLOSED
    assert b.state(T0) is expected


@given(outcomes=st.lists(st.booleans(), max_size=40))
def test_the_state_is_always_one_of_three(outcomes: list[bool]) -> None:
    b = _breaker(threshold=3)
    for ok in outcomes:
        if b.allows(T0):
            b.record_success(T0) if ok else b.record_failure(T0)
    assert b.state(T0) in set(BreakerState)


@given(outcomes=st.lists(st.booleans(), min_size=1, max_size=30))
def test_counters_never_disagree_with_the_calls_made(outcomes: list[bool]) -> None:
    b = _breaker(threshold=3)
    attempted = 0
    for ok in outcomes:
        if not b.allows(T0):
            continue
        attempted += 1
        b.record_success(T0) if ok else b.record_failure(T0)
    assert b.total_successes + b.total_failures == attempted


def test_reset_is_available_but_never_automatic() -> None:
    b = _breaker(threshold=2)
    _fail(b, 2)
    b.reset()
    assert b.state(T0) is BreakerState.CLOSED


def test_the_snapshot_explains_itself() -> None:
    b = _breaker(threshold=3, reset_seconds=30)
    _fail(b, 3)
    snap = b.snapshot(T0)
    assert snap["state"] == "open"
    assert snap["consecutive_failures"] == 3
    assert snap["retry_at"] is not None
    assert snap["times_opened"] == 1


# =============================================================================
# CLEARANCE NOTIFICATIONS
# =============================================================================


def test_three_reasons_a_road_stops_being_a_problem() -> None:
    assert {r.value for r in ClearanceReason} == {"resolved", "false_alarm", "expired"}


@pytest.mark.parametrize("reason", list(ClearanceReason))
def test_every_reason_reads_as_a_sentence(reason: ClearanceReason) -> None:
    msg = compose_clearance(IncidentType.FLOOD, "Spintex Road", reason)
    assert "Spintex Road" in msg
    assert msg.endswith(".")
    assert "_" not in msg


def test_a_false_alarm_reads_differently_from_a_resolution() -> None:
    """"We fixed it" and "there was nothing there" are different facts, and a commuter
    deciding whether to trust the next warning deserves to know which."""
    resolved = compose_clearance(IncidentType.ACCIDENT, "Ring Road", ClearanceReason.RESOLVED)
    false_alarm = compose_clearance(IncidentType.ACCIDENT, "Ring Road", ClearanceReason.FALSE_ALARM)
    assert resolved != false_alarm
    assert "could not be found" in false_alarm


def test_the_clearance_key_is_derived_and_stable() -> None:
    """Separate from the advisory key, so a clearance is a second notification rather
    than being swallowed by the warned-once constraint — but still deterministic, so
    replaying it warns nobody twice."""
    key = uuid.uuid4()
    assert _clearance_key(key) == _clearance_key(key)
    assert _clearance_key(key) != key


def test_stale_incidents_are_swept_well_after_they_have_faded() -> None:
    """Eight half-lives is a factor of 256. Erring on the side of keeping incidents a
    little too long is the right direction to err."""
    assert STALE_AFTER_HALF_LIVES >= 6
    assert 0.5 ** STALE_AFTER_HALF_LIVES < 0.01


def test_the_sweep_runs_often_enough_to_matter_and_rarely_enough_to_be_cheap() -> None:
    assert 60 <= SWEEP_INTERVAL_SECONDS <= 900
