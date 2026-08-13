"""The incident lifecycle — which moves are legal, and who may make them.

An incident passes through five states::

    reported ──▶ corroborated ──▶ verified ──▶ assigned ──▶ resolved
        ◀────────────┴───────────────┘            │
         (confidence can fall as well as rise)    └──▶ verified  (unassign)

Two kinds of transition, and the distinction is the important part of this module:

**Computed** — `reported`, `corroborated`, `verified`. Confidence decides these, and it
moves in both directions: an incident that nobody confirms decays back down on its own.
No human is involved.

**Decided** — `assigned` and `resolved`. A person did something. Arithmetic must never
produce or undo them, which is why the projector carries them across a rebuild rather
than recomputing them (see explainer 05).

Keeping the two apart is what stops a decaying confidence score quietly un-assigning a
warden who is already standing at the junction.


WHY A TABLE RATHER THAN `IF` STATEMENTS
---------------------------------------
The legal moves are data, in one dictionary. Anything absent from it is illegal by
construction — there is no code path to forget. Scattering the same rules through the
route handlers would mean the third handler someone adds is the one that forgets to
check whether the incident was ever assigned.

This module is pure: no database, no clock. It answers questions about states.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from app.models import IncidentStatus, UserRole


class Action(str, enum.Enum):
    """Something a person can do to an incident."""

    ASSIGN = "assign"        # officer sends a warden
    UNASSIGN = "unassign"    # officer recalls them
    RESOLVE = "resolve"      # the road is clear, or it never was blocked


class Resolution(str, enum.Enum):
    """How an incident ended. This is what drives reporter reputation.

    A confirmed incident raises the standing of everyone who reported it. A false alarm
    lowers it. Without both directions reputation could only ever go up, and a
    fabricated report would cost its author nothing.
    """

    CONFIRMED = "confirmed"
    FALSE_ALARM = "false_alarm"


class IllegalTransition(Exception):
    """The move is not permitted from this state. The message is safe to show a user."""


@dataclass(frozen=True)
class Rule:
    source: frozenset[IncidentStatus]
    target: IncidentStatus
    roles: frozenset[UserRole]
    description: str


# The whole state machine. Everything not listed here is impossible.
RULES: dict[Action, Rule] = {
    Action.ASSIGN: Rule(
        # Only from `verified`. That is what the escalation threshold means — an
        # officer should not be dispatching a warden to something the system does not
        # yet believe. If it matters and confidence is low, the answer is more
        # corroboration, not a lower bar.
        source=frozenset({IncidentStatus.VERIFIED}),
        target=IncidentStatus.ASSIGNED,
        roles=frozenset({UserRole.OFFICER, UserRole.ADMIN}),
        description="Send a warden to a verified incident",
    ),
    Action.UNASSIGN: Rule(
        source=frozenset({IncidentStatus.ASSIGNED}),
        target=IncidentStatus.VERIFIED,
        roles=frozenset({UserRole.OFFICER, UserRole.ADMIN}),
        description="Recall a warden, returning the incident to the queue",
    ),
    Action.RESOLVE: Rule(
        # Only from `assigned`. An incident cannot be closed by someone who never sent
        # anyone to look — that would let the queue be cleared by wishful thinking.
        source=frozenset({IncidentStatus.ASSIGNED}),
        target=IncidentStatus.RESOLVED,
        roles=frozenset({UserRole.WARDEN, UserRole.OFFICER, UserRole.ADMIN}),
        description="Confirm the road is clear, or that it was a false alarm",
    ),
}

# States confidence alone can produce. `assigned` and `resolved` are absent on purpose.
COMPUTED_STATES = frozenset(
    {IncidentStatus.REPORTED, IncidentStatus.CORROBORATED, IncidentStatus.VERIFIED}
)

DECIDED_STATES = frozenset({IncidentStatus.ASSIGNED, IncidentStatus.RESOLVED})

TERMINAL_STATES = frozenset({IncidentStatus.RESOLVED})


def is_legal(status: IncidentStatus, action: Action) -> bool:
    return status in RULES[action].source


def allowed_actions(status: IncidentStatus, role: UserRole) -> list[Action]:
    """What this person can do to an incident in this state.

    Used to drive the interface, so a button that would be refused is never offered.
    Presenting an action and then rejecting it is a worse experience than not
    presenting it.
    """
    return [
        action
        for action, rule in RULES.items()
        if status in rule.source and role in rule.roles
    ]


def next_status(status: IncidentStatus, action: Action, role: UserRole) -> IncidentStatus:
    """Apply an action, or explain precisely why it is not allowed.

    Order matters here. Permission is checked before legality, so a commuter poking at
    the API is told they lack the role rather than learning which states an incident can
    be in — the error message should not become a description of the state machine.
    """
    rule = RULES[action]

    if role not in rule.roles:
        names = ", ".join(sorted(r.value for r in rule.roles))
        raise IllegalTransition(
            f"Only {names} may {action.value} an incident. You are a {role.value}."
        )

    if status not in rule.source:
        legal_from = ", ".join(sorted(s.value for s in rule.source))
        raise IllegalTransition(
            f"Cannot {action.value} an incident that is {status.value}. "
            f"This is only possible from: {legal_from}."
        )

    return rule.target


def is_terminal(status: IncidentStatus) -> bool:
    return status in TERMINAL_STATES


def may_confidence_change(status: IncidentStatus) -> bool:
    """Whether recomputed confidence is allowed to move this incident's state.

    False once a human has acted. A warden already at the junction must not be recalled
    because the reports that summoned them have decayed — the decay is expected, and it
    says nothing about whether the road is still blocked.
    """
    return status in COMPUTED_STATES
