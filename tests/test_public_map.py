"""D-044 — what a signed-out visitor is allowed to see.

The map is the front door. Somebody who has just heard that Spintex is flooded should
reach the answer with no account, no navigation to learn, and no empty tabs for features
they cannot use.

So the line is drawn between **the road and the people**:

    SHOWN   -- what is blocking the road, roughly where, and how long ago
    GATED   -- who reported it, what they photographed or recorded, and the accuracy
               score built from their credibility

The score is gated for a reason worth stating on its own: it cannot be separated from the
people who produced it. It is a function of who reported the incident and how reliable
each of them has been, so publishing it beside a marker publishes a summary of their
credibility to anybody holding the link. `status` stays and carries the same judgement at
a coarser grain — *corroborated* means several people independently, *verified* means
enough that the police have been told.

These tests are about the gate being in the API. A gate the interface draws is a gate
anybody opens with curl.
"""

from __future__ import annotations

import datetime as dt
import inspect
import uuid

import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.models import Incident, IncidentStatus, IncidentType, User, UserRole
from app.routers.incidents import _to_response, get_incident, list_incidents
from app.schemas import IncidentResponse


def _incident(confidence: float = 0.82, reports: int = 6) -> Incident:
    now = dt.datetime.now(dt.timezone.utc)
    return Incident(
        id=uuid.uuid4(),
        incident_type=IncidentType.FLOOD,
        centroid=from_shape(Point(-0.187, 5.603), srid=4326),
        confidence=confidence,
        status=IncidentStatus.CORROBORATED,
        report_count=reports,
        first_reported_at=now,
        last_reported_at=now,
    )


def _viewer(role: UserRole = UserRole.COMMUTER) -> User:
    return User(
        id=uuid.uuid4(), email="a@b.demo", password_hash="x",
        display_name="A", role=role, reputation=0.5,
    )


# =============================================================================
# WHAT IS WITHHELD
# =============================================================================


def test_a_signed_out_visitor_gets_no_accuracy_score() -> None:
    assert _to_response(_incident(), None).confidence is None


def test_a_signed_out_visitor_is_not_told_how_many_people_reported_it() -> None:
    """The count is the size of the group the score was computed from. Withholding the
    score and publishing the group it came from concedes half the point."""
    assert _to_response(_incident(), None).report_count is None


@pytest.mark.parametrize(
    "role", [UserRole.COMMUTER, UserRole.WARDEN, UserRole.OFFICER, UserRole.ADMIN]
)
def test_anybody_signed_in_gets_both(role: UserRole) -> None:
    """The gate is about having an account, not about rank. A commuter who signs in is
    trusted with this; the distinction the system draws elsewhere is between roles, and
    this one deliberately is not."""
    response = _to_response(_incident(confidence=0.82, reports=6), _viewer(role))
    assert response.confidence == pytest.approx(0.82)
    assert response.report_count == 6


# =============================================================================
# WHAT IS KEPT
# =============================================================================


def test_the_road_is_still_described() -> None:
    """This is the promise in 02-problem-and-scope.md, and D-044 narrows it without
    breaking it: a commuter checking the road ahead still needs no account."""
    incident = _incident()
    public = _to_response(incident, None)

    assert public.incident_type is IncidentType.FLOOD
    assert public.latitude == pytest.approx(5.603)
    assert public.longitude == pytest.approx(-0.187)
    assert public.last_reported_at == incident.last_reported_at


def test_status_survives_because_it_is_the_score_banded() -> None:
    """Corroborated means several people independently; verified means enough that the
    police have been told. The visitor gets the conclusion without the working."""
    assert _to_response(_incident(), None).status is IncidentStatus.CORROBORATED


def test_the_map_is_the_same_map() -> None:
    """Only the arithmetic is private. If the public feed were also filtered or ordered
    differently, a signed-out visitor would be looking at a different city."""
    source = inspect.getsource(list_incidents)
    assert "viewer" in source
    # The ordering and the confidence floor are applied to the real column, not to
    # whatever survives into the response.
    assert "Incident.confidence >= min_confidence" in source
    assert "Incident.confidence.desc()" in source


# =============================================================================
# THE EVIDENCE IS DROPPED AT THE SOURCE
# =============================================================================


def test_the_detail_route_empties_the_evidence_before_building_it() -> None:
    """Not "renders nothing" — *loads* nothing.

    Dropping the rows before the attachment query means the bytes are never read and no
    signed URL is ever minted, so there is nothing in the response to leak by accident.
    Filtering afterwards would leave a list of attachment ids one refactor away from
    being serialised.
    """
    source = inspect.getsource(get_incident)
    gate = source.index("if viewer is None:")
    attachments = source.index("select(Attachment)")
    assert gate < attachments, "the evidence is loaded before the gate is applied"


def test_the_detail_route_knows_who_is_asking() -> None:
    assert "viewer" in inspect.signature(get_incident).parameters


# =============================================================================
# THE SHAPE OF THE RESPONSE
# =============================================================================


def test_the_two_gated_fields_are_optional_on_one_schema() -> None:
    """One shape with a field that is sometimes absent, rather than a public schema and
    a private one. Two schemas would be two places to forget."""
    for field in ("confidence", "report_count"):
        assert IncidentResponse.model_fields[field].default is None
        assert not IncidentResponse.model_fields[field].is_required()


def test_a_client_cannot_mistake_withheld_for_zero() -> None:
    """`None`, never `0.0`. A zero score is a real state — an incident that has decayed
    to nothing — and a client that renders "0%" for "not told" is showing a fact the
    server never asserted."""
    withheld = _to_response(_incident(confidence=0.9), None)
    decayed = _to_response(_incident(confidence=0.0), _viewer())

    assert withheld.confidence is None
    assert decayed.confidence == 0.0
