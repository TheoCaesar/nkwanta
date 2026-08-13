"""B04 — report intake, and the atomicity invariant.

The test that matters most in this file is
`test_report_and_outbox_are_added_before_a_single_commit`. It asserts the property the
whole advanced concept rests on: the report and the instruction to act on it are
written together, in one transaction, or not at all.

It works by recording the exact order of operations on a stubbed session. That is
deliberate — it tests the *guarantee*, not just the happy path, and it runs without
PostgreSQL so it can never be skipped for being slow.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.geo import (
    CoordinateError,
    haversine_metres,
    is_within_ghana,
    to_wkt_point,
    validate_coordinates,
)
from app.models import IncidentType, OutboxMessage, Report, User, UserRole
from app.schemas import ReportCreate
from app.services.reports import (
    EVENT_REPORT_SUBMITTED,
    MAX_REPORT_AGE,
    ReportRejected,
    build_outbox_message,
    submit_report,
)

ACCRA_LAT, ACCRA_LON = 5.6037, -0.1870      # Kwame Nkrumah Circle, near enough
NOW = dt.datetime(2026, 8, 13, 6, 40, tzinfo=dt.timezone.utc)


def _reporter() -> User:
    return User(
        id=uuid.uuid4(),
        email="kofi@example.com",
        password_hash="x",
        display_name="Kofi A.",
        role=UserRole.COMMUTER,
        reputation=0.5,
    )


def _body(**over) -> ReportCreate:
    data = dict(
        incident_type=IncidentType.ACCIDENT,
        latitude=ACCRA_LAT,
        longitude=ACCRA_LON,
        occurred_at=NOW,
    )
    data.update(over)
    return ReportCreate(**data)


class FakeSession:
    """Records what happened and in what order, so the invariant can be asserted."""

    def __init__(self, existing: Report | None = None) -> None:
        self.log: list[str] = []
        self.added: list[object] = []
        self._existing = existing

    async def scalar(self, _stmt):
        self.log.append("select")
        return self._existing

    def add(self, obj) -> None:
        self.log.append(f"add:{type(obj).__name__}")
        self.added.append(obj)

    async def commit(self) -> None:
        self.log.append("commit")

    async def rollback(self) -> None:
        self.log.append("rollback")

    async def refresh(self, _obj) -> None:
        self.log.append("refresh")


# =============================================================================
# THE INVARIANT
# =============================================================================


@pytest.mark.asyncio
async def test_report_and_outbox_are_added_before_a_single_commit() -> None:
    """The property the entire advanced concept rests on.

    Both rows must be added before any commit, and there must be exactly one commit.
    Two commits would reopen the crash window this design exists to close."""
    session = FakeSession()
    await submit_report(session, _reporter(), _body(), now=NOW)

    added_report = session.log.index("add:Report")
    added_outbox = session.log.index("add:OutboxMessage")
    first_commit = session.log.index("commit")

    assert added_report < first_commit
    assert added_outbox < first_commit
    assert session.log.count("commit") == 1


@pytest.mark.asyncio
async def test_exactly_one_report_and_one_outbox_row() -> None:
    session = FakeSession()
    await submit_report(session, _reporter(), _body(), now=NOW)

    assert sum(isinstance(o, Report) for o in session.added) == 1
    assert sum(isinstance(o, OutboxMessage) for o in session.added) == 1


@pytest.mark.asyncio
async def test_nothing_is_written_when_validation_fails() -> None:
    """A rejected report must not leave an orphan outbox row behind."""
    session = FakeSession()
    with pytest.raises(ReportRejected):
        await submit_report(session, _reporter(), _body(latitude=51.5, longitude=-0.12), now=NOW)

    assert session.added == []
    assert "commit" not in session.log


# =============================================================================
# IDEMPOTENCY
# =============================================================================


@pytest.mark.asyncio
async def test_repeat_of_a_known_key_returns_the_original() -> None:
    """A phone on a bad connection retries. The retry must not create a second report,
    or the incident's confidence is inflated by a network glitch."""
    original = Report(id=uuid.uuid4(), incident_type=IncidentType.ACCIDENT)
    session = FakeSession(existing=original)

    result = await submit_report(session, _reporter(), _body(idempotency_key="abc-123"), now=NOW)

    assert result.duplicate is True
    assert result.report is original
    assert session.added == []
    assert "commit" not in session.log


@pytest.mark.asyncio
async def test_no_key_means_no_deduplication_lookup() -> None:
    """Without a key there is nothing to match on, so intake must not waste a query."""
    session = FakeSession()
    await submit_report(session, _reporter(), _body(), now=NOW)
    assert "select" not in session.log


def test_outbox_key_is_derived_from_the_report_id() -> None:
    """Deterministic, not random: replaying intake for the same report produces the
    same key, so the same work can never be enqueued twice."""
    report = Report(id=uuid.uuid4(), reporter_id=uuid.uuid4(),
                    incident_type=IncidentType.FLOOD, occurred_at=NOW)
    a = build_outbox_message(report, ACCRA_LAT, ACCRA_LON)
    b = build_outbox_message(report, ACCRA_LAT, ACCRA_LON)

    assert a.idempotency_key == b.idempotency_key
    assert str(report.id) in a.idempotency_key
    assert a.event_type == EVENT_REPORT_SUBMITTED


def test_outbox_payload_carries_what_the_worker_needs() -> None:
    """The worker must not have to re-read the report to act on it."""
    report = Report(id=uuid.uuid4(), reporter_id=uuid.uuid4(),
                    incident_type=IncidentType.FLOOD, occurred_at=NOW)
    msg = build_outbox_message(report, ACCRA_LAT, ACCRA_LON)

    assert set(msg.payload) == {
        "report_id", "reporter_id", "incident_type", "latitude", "longitude", "occurred_at",
    }
    assert msg.payload["latitude"] == ACCRA_LAT


# =============================================================================
# VALIDATION
# =============================================================================


@pytest.mark.asyncio
async def test_location_outside_ghana_is_rejected() -> None:
    session = FakeSession()
    with pytest.raises(ReportRejected, match="outside Ghana"):
        await submit_report(session, _reporter(), _body(latitude=51.5, longitude=-0.12), now=NOW)


@pytest.mark.asyncio
async def test_swapped_coordinates_are_caught_by_the_ghana_check() -> None:
    """Accra reversed lands 600 km out in the Gulf of Guinea. Nothing crashes — which
    is exactly why this check exists."""
    session = FakeSession()
    with pytest.raises(ReportRejected, match="right way round"):
        await submit_report(
            session, _reporter(), _body(latitude=ACCRA_LON, longitude=ACCRA_LAT), now=NOW
        )


@pytest.mark.asyncio
async def test_future_report_is_rejected() -> None:
    session = FakeSession()
    with pytest.raises(ReportRejected, match="has not happened yet"):
        await submit_report(
            session, _reporter(), _body(occurred_at=NOW + dt.timedelta(hours=1)), now=NOW
        )


@pytest.mark.asyncio
async def test_small_clock_skew_is_tolerated() -> None:
    """Phone clocks drift. A minute into the future is drift, not a lie."""
    session = FakeSession()
    result = await submit_report(
        session, _reporter(), _body(occurred_at=NOW + dt.timedelta(seconds=60)), now=NOW
    )
    assert result.duplicate is False


@pytest.mark.asyncio
async def test_ancient_report_is_rejected() -> None:
    session = FakeSession()
    with pytest.raises(ReportRejected, match="24 hours"):
        await submit_report(
            session, _reporter(),
            _body(occurred_at=NOW - MAX_REPORT_AGE - dt.timedelta(minutes=1)), now=NOW,
        )


@pytest.mark.asyncio
async def test_naive_timestamp_is_treated_as_utc() -> None:
    """Ambiguous input must be resolved by a stated rule, not by a guess at the
    server's local zone — which would change behaviour with deployment region."""
    session = FakeSession()
    result = await submit_report(
        session, _reporter(), _body(occurred_at=dt.datetime(2026, 8, 13, 6, 39)), now=NOW
    )
    assert result.report.occurred_at.tzinfo is not None


@pytest.mark.asyncio
async def test_missing_timestamp_defaults_to_now() -> None:
    session = FakeSession()
    result = await submit_report(session, _reporter(), _body(occurred_at=None), now=NOW)
    assert result.report.occurred_at == NOW


# =============================================================================
# COORDINATES — the (lon, lat) trap
# =============================================================================


def test_wkt_puts_longitude_first() -> None:
    """PostGIS is (x, y) and longitude is x. Everyday speech is the other way round.
    Getting this backwards moves Accra into the sea without raising anything."""
    assert to_wkt_point(ACCRA_LAT, ACCRA_LON) == f"POINT({ACCRA_LON} {ACCRA_LAT})"


@pytest.mark.parametrize("lat,lon", [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_impossible_coordinates_rejected(lat: float, lon: float) -> None:
    with pytest.raises(CoordinateError):
        validate_coordinates(lat, lon)


def test_nan_rejected() -> None:
    with pytest.raises(CoordinateError):
        validate_coordinates(float("nan"), 0.0)


@pytest.mark.parametrize(
    "lat,lon,inside",
    [
        (ACCRA_LAT, ACCRA_LON, True),      # Accra
        (6.6885, -1.6244, True),           # Kumasi
        (9.4008, -0.8393, True),           # Tamale
        (51.5, -0.12, False),              # London
        (ACCRA_LON, ACCRA_LAT, False),     # Accra, reversed
    ],
)
def test_ghana_bounding_box(lat: float, lon: float, inside: bool) -> None:
    assert is_within_ghana(lat, lon) is inside


def test_haversine_matches_a_known_distance() -> None:
    """Accra to Kumasi is about 200 km in a straight line."""
    d = haversine_metres(ACCRA_LAT, ACCRA_LON, 6.6885, -1.6244)
    assert 195_000 < d < 210_000


def test_haversine_is_symmetric() -> None:
    a = haversine_metres(ACCRA_LAT, ACCRA_LON, 6.6885, -1.6244)
    b = haversine_metres(6.6885, -1.6244, ACCRA_LAT, ACCRA_LON)
    assert a == pytest.approx(b)


def test_haversine_of_a_point_with_itself_is_zero() -> None:
    assert haversine_metres(ACCRA_LAT, ACCRA_LON, ACCRA_LAT, ACCRA_LON) == pytest.approx(0.0)
