"""How much a reporter's word is worth.

Reputation is the defence against fabricated reports. Confidence weights each report by
its reporter's standing, so an account with a poor record cannot on its own push
anything to the police.

Until now reputation was a number that only ever sat still — seeded, never updated. This
closes the loop: when an officer or warden resolves an incident, everyone who reported it
is either vindicated or contradicted.


THE FORMULA
-----------
    reputation = (confirmed + PRIOR) / (confirmed + contradicted + 2 * PRIOR)

With PRIOR = 2, a brand-new account sits at 2/4 = 0.5 — neither trusted nor distrusted.

This is the mean of a **Beta posterior**, the standard Bayesian way to estimate a
probability from successes and failures. The plain-language version: start everyone at a
coin flip, and give that starting assumption the weight of two imaginary confirmed
reports and two imaginary contradicted ones. Real outcomes then pull the number away
from 0.5, slowly at first and faster as evidence accumulates.

Why not simply confirmed / (confirmed + contradicted)?

Because a single confirmed report would give 1/1 = **1.0**, total trust from one lucky
guess, and one contradicted report would give 0.0, permanent damnation from one mistake.
Both are absurd, and both are exactly what an attacker would exploit: file one true
report, become fully trusted, then fabricate.

The prior fixes it. One confirmed report moves a new account from 0.50 to 0.60, not to
1.0. Reaching 0.9 takes roughly eighteen confirmations with no contradictions.
"""

from __future__ import annotations

from dataclasses import dataclass

# The weight of the "everyone starts at a coin flip" assumption, measured in imaginary
# observations. Larger means reputation moves more slowly and is harder to game;
# smaller means it responds faster to genuine track record. Two is a compromise, and
# like every other constant here it is fitted to no data — see TD-04.
PRIOR = 2.0

# Reputation is deliberately not allowed to reach 0.0 or 1.0. Nobody is certain, and a
# reporter at exactly 0.0 could never recover — every report they filed would carry zero
# weight, so none could ever be confirmed. That is a trap with no exit.
MIN_REPUTATION = 0.02
MAX_REPUTATION = 0.98


@dataclass(frozen=True)
class ReputationUpdate:
    confirmed: int
    contradicted: int
    reputation: float


def compute(confirmed: int, contradicted: int) -> float:
    """Reputation from a reporter's record."""
    if confirmed < 0 or contradicted < 0:
        raise ValueError("counts cannot be negative")

    raw = (confirmed + PRIOR) / (confirmed + contradicted + 2 * PRIOR)
    return min(MAX_REPUTATION, max(MIN_REPUTATION, raw))


def after_confirmation(confirmed: int, contradicted: int) -> ReputationUpdate:
    """Their report was borne out by someone who went and looked."""
    return ReputationUpdate(
        confirmed=confirmed + 1,
        contradicted=contradicted,
        reputation=compute(confirmed + 1, contradicted),
    )


def after_contradiction(confirmed: int, contradicted: int) -> ReputationUpdate:
    """A warden attended and found nothing. Costly, but survivable.

    Note this is not a fraud judgement. Honest people misjudge, and a road can clear
    before anyone arrives. Which is why one contradiction costs about a tenth of a
    point rather than being fatal, and why reputation can never reach zero.
    """
    return ReputationUpdate(
        confirmed=confirmed,
        contradicted=contradicted + 1,
        reputation=compute(confirmed, contradicted + 1),
    )


def trajectory(outcomes: list[bool]) -> list[float]:
    """Reputation after each outcome in turn. Used in tests and documentation to show
    how quickly trust is earned and lost."""
    confirmed = contradicted = 0
    out = []
    for ok in outcomes:
        if ok:
            confirmed += 1
        else:
            contradicted += 1
        out.append(compute(confirmed, contradicted))
    return out
