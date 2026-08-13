"""D — the demonstration data.

Seed data is usually untested, and usually that is fine. Here it is not: this is the
data an examiner will look at, and two of its properties are load-bearing.

**Timestamps must be relative to run time.** Confidence halves every 45 minutes, so
fixed timestamps would leave the map blank whenever anyone actually looked.

**Ids must be deterministic.** A seed script that duplicates its data on every run is
worse than no seed script.

These run without a database — they check the seed *definitions*, which is where the
mistakes would be.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.geo import is_within_ghana
from app.models import IncidentType, UserRole
from app.services.seed import (
    DEMO_EMAIL_DOMAIN,
    DEMO_PASSWORD,
    PLACES,
    SEED_REPORTS,
    SEED_USERS,
    _id,
    _offset,
)


# --- accounts -----------------------------------------------------------------


def test_the_four_documented_accounts_exist() -> None:
    """These are the credentials printed in Deployment_and_Source_Links.txt. If they
    stop matching, the examiner cannot log in."""
    keys = {u.key for u in SEED_USERS}
    assert {"commuter", "warden", "officer", "admin"} <= keys


def test_every_role_is_represented() -> None:
    assert {u.role for u in SEED_USERS} == set(UserRole)


def test_account_keys_are_unique() -> None:
    keys = [u.key for u in SEED_USERS]
    assert len(keys) == len(set(keys))


def test_reputations_span_a_useful_range() -> None:
    """Without a spread, every incident scores the same and the reputation weighting is
    invisible in the demonstration."""
    reps = [u.reputation for u in SEED_USERS]
    assert min(reps) < 0.2
    assert max(reps) > 0.85
    assert all(0.0 <= r <= 1.0 for r in reps)


def test_there_are_discredited_accounts() -> None:
    """The anti-fabrication case needs someone to fabricate."""
    assert any(u.reputation < 0.2 for u in SEED_USERS)


def test_demo_password_meets_the_registration_rules() -> None:
    assert len(DEMO_PASSWORD) >= 8
    assert len(DEMO_PASSWORD.encode()) <= 72


# --- determinism --------------------------------------------------------------


def test_generated_ids_are_stable_across_calls() -> None:
    """uuid5 from a fixed namespace. Re-running the seed updates rather than
    duplicates."""
    assert _id("user", "kofi") == _id("user", "kofi")
    assert _id("user", "kofi") != _id("user", "adjoa")
    assert _id("user", "kofi") != _id("report", "kofi")


def test_every_report_key_is_unique() -> None:
    """Two reports sharing a key would collide and one would silently vanish."""
    keys = [f"{r.place}:{r.reporter_key}:{r.minutes_ago}" for r in SEED_REPORTS]
    assert len(keys) == len(set(keys))


# --- places -------------------------------------------------------------------


def test_every_place_is_inside_ghana() -> None:
    """Catches a latitude/longitude swap in the coordinate table, which would otherwise
    put half of Accra in the Gulf of Guinea."""
    for name, (lat, lon) in PLACES.items():
        assert is_within_ghana(lat, lon), f"{name} at ({lat}, {lon}) is outside Ghana"


def test_places_are_plausibly_in_greater_accra() -> None:
    for name, (lat, lon) in PLACES.items():
        assert 5.4 <= lat <= 5.8, f"{name} latitude looks wrong"
        assert -0.5 <= lon <= 0.1, f"{name} longitude looks wrong"


def test_there_are_enough_places_to_look_like_a_city() -> None:
    assert len(PLACES) >= 15


def test_offset_moves_roughly_the_right_distance() -> None:
    from app.geo import haversine_metres

    lat, lon = PLACES["Kwame Nkrumah Circle"]
    moved_lat, moved_lon = _offset(lat, lon, 100.0, 0.0)
    assert haversine_metres(lat, lon, moved_lat, moved_lon) == pytest.approx(100, abs=2)


# --- the scenario -------------------------------------------------------------


def test_every_report_references_a_real_place_and_reporter() -> None:
    keys = {u.key for u in SEED_USERS}
    for r in SEED_REPORTS:
        assert r.place in PLACES, f"unknown place {r.place}"
        assert r.reporter_key in keys, f"unknown reporter {r.reporter_key}"


def test_all_six_incident_types_appear() -> None:
    """The demonstration should show the full range, not three accidents."""
    assert {r.incident_type for r in SEED_REPORTS} == set(IncidentType)


def test_there_is_a_large_multi_reporter_incident() -> None:
    """Something has to be clearly verified, or the escalation path is invisible."""
    from collections import Counter

    counts = Counter((r.place, r.incident_type) for r in SEED_REPORTS)
    assert max(counts.values()) >= 5


def test_there_are_isolated_single_reports() -> None:
    """Most real reports are lone ones. A map where everything clusters is a fiction."""
    from collections import Counter

    counts = Counter((r.place, r.incident_type) for r in SEED_REPORTS)
    assert sum(1 for c in counts.values() if c == 1) >= 5


def test_a_discredited_reporter_files_something_alone() -> None:
    """The case that demonstrates reputation doing its job."""
    doubtful = {u.key for u in SEED_USERS if u.reputation < 0.2}
    from collections import Counter

    counts = Counter((r.place, r.incident_type) for r in SEED_REPORTS)
    solo = {k for k, c in counts.items() if c == 1}
    assert any(
        (r.place, r.incident_type) in solo and r.reporter_key in doubtful
        for r in SEED_REPORTS
    )


def test_reports_span_fresh_and_fading() -> None:
    """Confidence decay is only visible if some reports are old enough to have faded."""
    ages = [r.minutes_ago for r in SEED_REPORTS]
    assert min(ages) <= 10
    assert max(ages) >= 90


def test_nothing_is_older_than_intake_would_accept() -> None:
    """Intake rejects reports over 24 hours old. Seeded data must obey the same rule
    it enforces on everyone else."""
    assert max(r.minutes_ago for r in SEED_REPORTS) < 24 * 60


def test_there_are_enough_reports_to_look_like_a_system() -> None:
    assert len(SEED_REPORTS) >= 30


def test_emails_use_a_reserved_demonstration_domain() -> None:
    """`.demo` is not a real TLD, so these addresses cannot collide with a real person
    and cannot receive mail by accident."""
    assert DEMO_EMAIL_DOMAIN.endswith(".demo")
