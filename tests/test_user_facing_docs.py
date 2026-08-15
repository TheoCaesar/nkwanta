"""The user manual and the evolution plan have to be true too.

A manual is the document most likely to rot, because it describes behaviour rather than
structure and nothing breaks when it drifts. It is also the one a user trusts most
literally: if it says a limit is 8 characters and the code says 10, the user is simply
locked out with no explanation.

So the manual's factual claims are checked against the constants, and the evolution plan's
citations are checked against the registers they cite.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MANUAL = (DOCS / "13-user-manual.md").read_text(encoding="utf-8")
EVOLUTION = (DOCS / "12-maintenance-and-evolution.md").read_text(encoding="utf-8")


# =============================================================================
# THE MANUAL
# =============================================================================


def test_the_safety_note_comes_before_anything_else() -> None:
    """NFR-03 and NFR-05. A manual that explains reporting before it says "not while
    driving" has put the instruction where nobody reads it."""
    head = MANUAL[:1200]
    assert "Never use this while driving" in head
    assert "does not call the police" in head.lower() or "not call the police" in head.lower()


def test_it_does_not_claim_the_system_summons_help() -> None:
    """NFR-05 — liability, and honesty about what the system does."""
    for phrase in ("calls an ambulance", "dispatches emergency", "summons the police"):
        assert phrase not in MANUAL.lower(), f"the manual claims it {phrase}"


def test_the_password_rule_it_states_matches_the_code() -> None:
    """The most literally trusted sentence in any manual."""
    from app.schemas import RegisterRequest

    field = RegisterRequest.model_fields["password"]
    minimum = next(
        (getattr(m, "min_length", None) for m in field.metadata
         if getattr(m, "min_length", None) is not None), None
    )
    assert minimum is not None, "the password field no longer states a minimum length"

    words = {"eight": 8, "nine": 9, "ten": 10, "twelve": 12}
    # `\s+`, not a space: the manual is hard-wrapped and the number lands on the next
    # line as often as not. A regex that assumes one line tests the typography.
    match = re.search(r"at least\s+(\w+)\s+characters", MANUAL)
    assert match, "the manual no longer states a password length at all"
    raw = match.group(1)
    stated = words.get(raw.lower(), int(raw) if raw.isdigit() else None)
    assert stated == minimum, f"manual says {raw}, code requires {minimum}"


def test_the_thresholds_it_quotes_match_the_code() -> None:
    from app.confidence import THRESHOLD_VERIFIED

    assert f"{THRESHOLD_VERIFIED:.0%}".replace("%", "%") in MANUAL or "70%" in MANUAL
    assert THRESHOLD_VERIFIED == 0.70, "the manual's 70% is now wrong"


def test_the_decay_it_describes_matches_the_code() -> None:
    from app.confidence import DEFAULT_HALF_LIFE_MINUTES

    assert f"{int(DEFAULT_HALF_LIFE_MINUTES)} minutes" in MANUAL


def test_every_incident_type_is_described() -> None:
    """Six types, and a manual naming five leaves a user hunting for the missing one."""
    from app.models import IncidentType

    described = MANUAL.lower()
    for kind in IncidentType:
        words = kind.value.split("_")
        assert any(w in described for w in words), f"{kind.value} is not described"


def test_every_demonstration_account_it_lists_is_seeded() -> None:
    """These are the credentials an examiner types. If one is wrong they cannot get in."""
    from app.services.seed import DEMO_EMAIL_DOMAIN, DEMO_PASSWORD, SEED_USERS

    seeded = {f"{u.key}@{DEMO_EMAIL_DOMAIN}" for u in SEED_USERS}
    listed = set(re.findall(r"`([\w.]+@nkwanta\.demo)`", MANUAL))
    assert listed, "the manual lists no demonstration accounts"
    assert listed <= seeded, f"listed but never seeded: {sorted(listed - seeded)}"
    assert DEMO_PASSWORD in MANUAL, "the stated password is not the seeded one"


def test_it_states_the_privacy_rules_the_system_actually_enforces() -> None:
    """A manual promising more privacy than the code delivers is the worst kind of error
    in this particular document."""
    lowered = MANUAL.lower()
    assert "private unless you choose to share it" in lowered      # NFR-04a, D-029
    assert "never identified" in lowered                            # NFR-04
    assert "shared by default" in lowered                           # D-042, stated plainly


def test_it_tells_the_user_a_report_cannot_be_deleted() -> None:
    """Reports are append-only. Someone who expects to delete one and cannot will assume
    the application is broken."""
    assert "permanent" in MANUAL.lower()
    assert re.search(r"can i delete a report", MANUAL, re.I)


# =============================================================================
# MAINTENANCE AND EVOLUTION
# =============================================================================


def test_the_plan_covers_lehmans_laws() -> None:
    """Named in the course and directly relevant to this section of the mark scheme."""
    assert "Lehman" in EVOLUTION
    for law in ("continuing change", "increasing complexity", "declining quality"):
        assert law in EVOLUTION.lower(), f"{law} is not addressed"


def test_the_four_maintenance_categories_are_covered() -> None:
    for category in ("corrective", "adaptive", "perfective", "preventive"):
        assert category in EVOLUTION.lower(), f"{category} maintenance is not covered"


def test_every_debt_item_in_the_repayment_plan_is_registered() -> None:
    debt = (DOCS / "08-technical-debt.md").read_text(encoding="utf-8")
    cited = set(re.findall(r"\bTD-(\d{2})\b", EVOLUTION))
    assert len(cited) >= 10, "a repayment plan citing three items is not a plan"
    for number in sorted(cited):
        assert f"TD-{number}" in debt, f"TD-{number} is scheduled but not registered"


def test_both_critical_debt_items_are_scheduled_first() -> None:
    """The register classifies two items as C — needing attention before any real user.
    A plan that schedules them anywhere but first disagrees with its own register."""
    debt = (DOCS / "08-technical-debt.md").read_text(encoding="utf-8")
    critical = set(re.findall(r"\| (TD-\d{2}) \| [^|]+ \| \*\*C\*\* \|", debt))
    assert critical, "no critical items found; the register format may have changed"

    release_one = EVOLUTION[EVOLUTION.index("Release 1"):EVOLUTION.index("Release 2")]
    for item in sorted(critical):
        assert item in release_one, f"{item} is Critical and is not in the first release"


def test_the_partial_requirement_is_named_here_too() -> None:
    """Clearance. Three documents now admit it; none may quietly drop it."""
    assert "FR-40" in EVOLUTION


def test_the_excluded_feature_stays_excluded() -> None:
    """Ride-sharing was the largest scope risk in the original brief. An evolution plan
    that quietly reinstates it undoes the requirements decision it was cut by."""
    section = EVOLUTION[EVOLUTION.index("6.5"):]
    assert "separate system" in section.lower() or "should stay excluded" in section.lower()
