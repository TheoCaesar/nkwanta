"""B08 — the lifecycle state machine and reputation feedback.

The state machine turns a class of bug into an impossibility. Rather than checking "was
this incident ever assigned?" in each route handler and hoping none is forgotten, the
legal moves live in one table and everything absent from it is refused.

The tests fall into two groups:

    LEGALITY   -- which moves are allowed from which states, and to whom
    REPUTATION -- that trust is earned slowly, lost meaningfully, and never absolute
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.lifecycle import (
    COMPUTED_STATES,
    DECIDED_STATES,
    RULES,
    Action,
    IllegalTransition,
    Resolution,
    allowed_actions,
    is_legal,
    is_terminal,
    may_confidence_change,
    next_status,
)
from app.models import IncidentStatus, UserRole
from app.reputation import (
    MAX_REPUTATION,
    MIN_REPUTATION,
    PRIOR,
    after_confirmation,
    after_contradiction,
    compute,
    trajectory,
)

statuses = st.sampled_from(list(IncidentStatus))
roles = st.sampled_from(list(UserRole))
actions = st.sampled_from(list(Action))


# =============================================================================
# THE SHAPE OF THE MACHINE
# =============================================================================


def test_computed_and_decided_states_do_not_overlap() -> None:
    """The central distinction. Confidence produces the first three; a person produces
    the last two. If they overlapped, a decaying score could un-assign a warden who is
    already standing at the junction."""
    assert COMPUTED_STATES & DECIDED_STATES == set()
    assert COMPUTED_STATES | DECIDED_STATES == set(IncidentStatus)


def test_assigned_and_resolved_are_never_computed() -> None:
    assert IncidentStatus.ASSIGNED not in COMPUTED_STATES
    assert IncidentStatus.RESOLVED not in COMPUTED_STATES


@given(status=statuses)
def test_confidence_may_only_move_uncommitted_incidents(status) -> None:
    assert may_confidence_change(status) == (status in COMPUTED_STATES)


def test_resolved_is_terminal() -> None:
    assert is_terminal(IncidentStatus.RESOLVED)
    for action in Action:
        assert not is_legal(IncidentStatus.RESOLVED, action)


# =============================================================================
# LEGALITY
# =============================================================================


def test_a_verified_incident_can_be_assigned() -> None:
    assert next_status(IncidentStatus.VERIFIED, Action.ASSIGN, UserRole.OFFICER) == (
        IncidentStatus.ASSIGNED
    )


@pytest.mark.parametrize(
    "status", [IncidentStatus.REPORTED, IncidentStatus.CORROBORATED]
)
def test_an_unverified_incident_cannot_be_assigned(status) -> None:
    """The escalation threshold has to mean something. If an officer could dispatch to
    anything, confidence would be decoration."""
    with pytest.raises(IllegalTransition, match="Cannot assign"):
        next_status(status, Action.ASSIGN, UserRole.OFFICER)


def test_an_incident_cannot_be_resolved_without_being_assigned() -> None:
    """Otherwise the queue could be cleared by wishful thinking, without anyone going
    to look."""
    with pytest.raises(IllegalTransition):
        next_status(IncidentStatus.VERIFIED, Action.RESOLVE, UserRole.OFFICER)


def test_unassigning_returns_an_incident_to_the_queue() -> None:
    assert next_status(IncidentStatus.ASSIGNED, Action.UNASSIGN, UserRole.OFFICER) == (
        IncidentStatus.VERIFIED
    )


def test_a_commuter_can_do_nothing_at_all() -> None:
    for action in Action:
        with pytest.raises(IllegalTransition, match="Only"):
            next_status(IncidentStatus.VERIFIED, action, UserRole.COMMUTER)


def test_a_warden_cannot_assign_work_to_themselves() -> None:
    """Deciding who goes is the officer's job. A warden who could self-assign could
    cherry-pick, and the dispatch queue would stop reflecting priority."""
    with pytest.raises(IllegalTransition, match="Only"):
        next_status(IncidentStatus.VERIFIED, Action.ASSIGN, UserRole.WARDEN)


def test_a_warden_may_resolve() -> None:
    assert next_status(IncidentStatus.ASSIGNED, Action.RESOLVE, UserRole.WARDEN) == (
        IncidentStatus.RESOLVED
    )


def test_permission_is_reported_before_legality() -> None:
    """A commuter is told they lack the role, not which states an incident can be in.
    An error message should not double as documentation of the state machine."""
    with pytest.raises(IllegalTransition, match="Only"):
        next_status(IncidentStatus.REPORTED, Action.ASSIGN, UserRole.COMMUTER)


@given(status=statuses, action=actions, role=roles)
def test_every_combination_either_transitions_or_explains_itself(status, action, role) -> None:
    """No combination may crash, and no refusal may be silent."""
    try:
        result = next_status(status, action, role)
        assert result in IncidentStatus
        assert result == RULES[action].target
    except IllegalTransition as exc:
        assert str(exc)


@given(status=statuses, role=roles)
def test_allowed_actions_agrees_with_what_actually_succeeds(status, role) -> None:
    """The interface is driven by `allowed_actions`, so if it disagreed with the guard a
    user would be offered a button that then refuses them."""
    offered = set(allowed_actions(status, role))
    for action in Action:
        try:
            next_status(status, action, role)
            assert action in offered
        except IllegalTransition:
            assert action not in offered


def test_a_commuter_is_offered_nothing() -> None:
    for status in IncidentStatus:
        assert allowed_actions(status, UserRole.COMMUTER) == []


# =============================================================================
# REPUTATION
# =============================================================================


def test_a_new_account_starts_at_a_coin_flip() -> None:
    assert compute(0, 0) == pytest.approx(0.5)


def test_one_confirmation_does_not_confer_total_trust() -> None:
    """Without the prior this would be 1/1 = 1.0 — total trust from one lucky guess,
    which is exactly what an attacker would exploit: file one true report, become fully
    trusted, then fabricate."""
    assert compute(1, 0) == pytest.approx((1 + PRIOR) / (1 + 2 * PRIOR))
    assert compute(1, 0) < 0.65


def test_one_mistake_is_not_fatal() -> None:
    """Honest people misjudge, and a road can clear before anyone arrives."""
    assert compute(0, 1) > 0.3


def test_reputation_never_reaches_zero() -> None:
    """A reporter at exactly zero could never recover: every report would carry zero
    weight, so none could ever be confirmed. That is a trap with no exit."""
    assert compute(0, 10_000) >= MIN_REPUTATION
    assert compute(0, 10_000) > 0


def test_reputation_never_reaches_one() -> None:
    assert compute(10_000, 0) <= MAX_REPUTATION
    assert compute(10_000, 0) < 1.0


@given(
    confirmed=st.integers(0, 500),
    contradicted=st.integers(0, 500),
)
def test_reputation_is_always_a_valid_weight(confirmed, contradicted) -> None:
    assert MIN_REPUTATION <= compute(confirmed, contradicted) <= MAX_REPUTATION


@given(confirmed=st.integers(0, 200), contradicted=st.integers(0, 200))
def test_a_confirmation_never_lowers_reputation(confirmed, contradicted) -> None:
    before = compute(confirmed, contradicted)
    assert after_confirmation(confirmed, contradicted).reputation >= before


@given(confirmed=st.integers(0, 200), contradicted=st.integers(0, 200))
def test_a_contradiction_never_raises_reputation(confirmed, contradicted) -> None:
    before = compute(confirmed, contradicted)
    assert after_contradiction(confirmed, contradicted).reputation <= before


@given(n=st.integers(1, 100))
def test_more_confirmations_are_monotonically_better(n) -> None:
    assert compute(n, 0) >= compute(n - 1, 0)


def test_trust_is_earned_slowly() -> None:
    """Eighteen consecutive confirmations to pass 0.9. Reputation should be expensive
    to build, or it is not worth anything."""
    path = trajectory([True] * 20)
    assert path[0] < 0.65
    assert path[4] < 0.85
    assert path[-1] > 0.9


def test_trust_is_lost_faster_than_it_is_gained() -> None:
    """Five confirmations then three false alarms should hurt visibly. An asymmetry
    here is deliberate — the cost of a false report must exceed the benefit of a true
    one, or fabricating is profitable in expectation."""
    good = trajectory([True] * 5)[-1]
    then_bad = trajectory([True] * 5 + [False] * 3)[-1]
    assert then_bad < good - 0.15


def test_counts_cannot_be_negative() -> None:
    with pytest.raises(ValueError):
        compute(-1, 0)


def test_resolution_has_exactly_two_outcomes() -> None:
    """Both directions are required. If an incident could only ever be confirmed,
    reputation could only rise and fabricating would cost nothing."""
    assert {r.value for r in Resolution} == {"confirmed", "false_alarm"}
