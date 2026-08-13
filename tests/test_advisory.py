"""B — corridor matching and the commuter advisory.

The advisory is the first thing the outbox delivers that a *user* can see. Until now it
carried instructions that only rebuilt internal state.

Three things are being checked:

    THRESHOLDS  -- commuters are warned earlier than police are called, deliberately
    MESSAGES    -- what a commuter reads is words, not a number
    FAN-OUT     -- one advisory becomes one notification per person, exactly once
"""

from __future__ import annotations

import uuid

import pytest

from app.confidence import THRESHOLD_CORROBORATED, THRESHOLD_VERIFIED
from app.models import (
    Corridor,
    CorridorSubscription,
    IncidentType,
    Notification,
)
from app.services.advisory import (
    ADVISORY_THRESHOLD,
    CORRIDOR_MATCH_METRES,
    EVENT_INCIDENT_ADVISORY,
    compose_message,
)
from app.services.seed import SEED_CORRIDORS, SEED_SUBSCRIPTIONS, _linestring


# =============================================================================
# THRESHOLDS
# =============================================================================


def test_commuters_are_warned_before_police_are_called() -> None:
    """Not an inconsistency — the two decisions have different costs.

    Sending a warden to nothing wastes someone who was needed elsewhere. Telling a
    commuter about something that turns out to be clear costs them a glance at the map.
    When the price of being wrong differs that much, the threshold should differ too.
    """
    assert ADVISORY_THRESHOLD < THRESHOLD_VERIFIED
    assert ADVISORY_THRESHOLD == THRESHOLD_CORROBORATED


def test_a_lone_unconfirmed_report_warns_nobody() -> None:
    """One report from an average account scores about 0.225. Warning a whole corridor
    on one person's word would make the system noise."""
    assert 0.225 < ADVISORY_THRESHOLD


def test_the_match_radius_is_generous_but_not_absurd() -> None:
    """Wide enough to catch the far carriageway or just off a junction; tight enough
    that a parallel street does not trigger."""
    assert 100 <= CORRIDOR_MATCH_METRES <= 400


# =============================================================================
# WHAT A COMMUTER READS
# =============================================================================


def test_the_message_names_the_road_and_the_problem() -> None:
    msg = compose_message(IncidentType.ACCIDENT, "Spintex Road", 0.85)
    assert "Spintex Road" in msg
    assert "accident" in msg.lower()


def test_confidence_is_expressed_in_words_not_numbers() -> None:
    """"0.42" means nothing to someone deciding whether to leave early. The number is
    still on the incident for anyone who wants it."""
    msg = compose_message(IncidentType.FLOOD, "Ring Road", 0.42)
    assert "0.42" not in msg
    assert "reported" in msg


@pytest.mark.parametrize(
    "confidence,expected",
    [(0.40, "not yet confirmed"), (0.55, "more than one person"), (0.85, "several people")],
)
def test_stronger_evidence_reads_more_strongly(confidence: float, expected: str) -> None:
    assert expected in compose_message(IncidentType.ACCIDENT, "N1 Motorway", confidence)


@pytest.mark.parametrize("kind", list(IncidentType))
def test_every_incident_type_has_readable_wording(kind: IncidentType) -> None:
    """A message reading "A surface_defect on Ring Road" would be an obvious leak of
    an internal identifier."""
    msg = compose_message(kind, "Ring Road", 0.6)
    assert "_" not in msg.split("—")[0]
    assert msg[0].isupper()


def test_messages_fit_the_column() -> None:
    longest_road = max(SEED_CORRIDORS, key=len)
    for kind in IncidentType:
        assert len(compose_message(kind, longest_road, 0.9)) <= 300


# =============================================================================
# DELIVERED ONCE
# =============================================================================


def test_a_person_is_warned_once_per_incident() -> None:
    """The constraint that makes at-least-once delivery survivable. The worker may
    replay an advisory after a crash, a retry or a rebuild."""
    names = {c.name for c in Notification.__table__.constraints if c.name}
    assert "uq_notifications_once_per_incident" in names


def test_notifications_key_on_the_cluster_key_not_the_incident_id() -> None:
    """Incident rows are deleted and recreated on every rebuild, so their ids are
    useless as identity. The cluster key survives because membership is
    order-independent."""
    assert "incident_key" in Notification.__table__.columns
    assert "incident_id" not in Notification.__table__.columns


def test_following_the_same_road_twice_is_impossible() -> None:
    pk = {c.name for c in CorridorSubscription.__table__.primary_key.columns}
    assert pk == {"user_id", "corridor_id"}


def test_the_advisory_event_has_a_stable_name() -> None:
    from app.worker import HANDLERS

    assert EVENT_INCIDENT_ADVISORY in HANDLERS


# =============================================================================
# CORRIDORS ARE LINES
# =============================================================================


def test_a_corridor_is_a_line_not_a_point() -> None:
    """"Is this incident on my route?" is a question about distance from a line. A
    corridor modelled as a centre point with a radius could not answer it — a circle
    covering the 20 km Tema Motorway would cover half of Accra."""
    col = Corridor.__table__.columns["path"]
    assert col.type.geometry_type == "LINESTRING"
    assert col.type.srid == 4326


def test_corridors_have_a_spatial_index() -> None:
    ix = next(i for i in Corridor.__table__.indexes if i.name == "ix_corridors_path")
    assert ix.dialect_options["postgresql"]["using"] == "gist"


def test_linestring_wkt_puts_longitude_first() -> None:
    """Same trap as POINT. A swap here would lay every road out in the Gulf of Guinea
    and nothing would raise."""
    wkt = _linestring([(5.6180, -0.1720), (5.6280, -0.0930)])
    assert wkt == "LINESTRING(-0.172 5.618, -0.093 5.628)"


# =============================================================================
# THE SEEDED SCENARIO
# =============================================================================


def test_enough_corridors_to_cover_the_city() -> None:
    assert len(SEED_CORRIDORS) >= 12


def test_every_corridor_has_at_least_two_points() -> None:
    for name, (_, points) in SEED_CORRIDORS.items():
        assert len(points) >= 2, f"{name} is not a line"


def test_every_corridor_point_is_inside_ghana() -> None:
    from app.geo import is_within_ghana

    for name, (_, points) in SEED_CORRIDORS.items():
        for lat, lon in points:
            assert is_within_ghana(lat, lon), f"{name} has a point outside Ghana"


def test_every_subscription_names_a_real_corridor_and_user() -> None:
    users = {u.key for u in __import__("app.services.seed", fromlist=["SEED_USERS"]).SEED_USERS}
    for user_key, roads in SEED_SUBSCRIPTIONS.items():
        assert user_key in users, f"unknown user {user_key}"
        for road in roads:
            assert road in SEED_CORRIDORS, f"unknown corridor {road}"


def test_the_demonstration_will_produce_notifications() -> None:
    """Several commuters follow the roads where the two verified incidents sit. Without
    this the advisory feature would demonstrate an empty list."""
    followers_of_hotspots = [
        user for user, roads in SEED_SUBSCRIPTIONS.items()
        if "Ring Road" in roads or "Achimota–Circle" in roads
    ]
    assert len(followers_of_hotspots) >= 5
