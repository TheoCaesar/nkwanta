"""End-to-end pipeline test — requires a real PostGIS database.

Everything else in the suite runs against stubs and pure functions, which is fast and
catches most things. It cannot catch what only a real database can: whether
`ST_DWithin` is measuring metres, whether the geography column round-trips coordinates
in the right order, whether the cascade deletes behave.

So this file exercises the whole chain for real:

    POST a report -> outbox row written in the same transaction
                  -> worker claims it
                  -> neighbourhood fetched with a live PostGIS query
                  -> clustering and confidence run
                  -> incident written and readable

**Skipped automatically when DATABASE_URL is not set**, so `pytest` still passes on a
machine with no database. Run it deliberately:

    pytest tests/test_integration_pipeline.py -v

Everything it creates is deleted afterwards, including when an assertion fails.


A WARNING THESE TESTS LEARNED THE HARD WAY
------------------------------------------
Development and production share one Neon database (TD-18), and **both run an outbox
worker**. So while these tests are running, something else may be draining the same queue.

That is not a flaw to be worked around with sleeps — it is the real deployment, and a
test that only passes when the rest of the system is switched off is testing the wrong
thing. Assertions here are therefore about *what must be true*, not about *what has not
happened yet*: that a row exists and is correctly linked, rather than that nobody has
touched it.

One test asserted the latter, passed for a whole session, and failed the moment the
application was actually running.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.confidence import THRESHOLD_CORROBORATED
from app.models import (
    Incident,
    IncidentReport,
    IncidentType,
    OutboxMessage,
    Report,
    User,
    UserRole,
)
from app.schemas import ReportCreate
from app.security import hash_password
from app.services.reports import submit_report
from app.worker import OutboxWorker

pytestmark = pytest.mark.skipif(
    not get_settings().database_configured,
    reason="no DATABASE_URL configured — integration tests skipped",
)

# Kwame Nkrumah Circle. Three points within about 100 m of each other.
CIRCLE = [
    (5.60370, -0.18700),
    (5.60415, -0.18740),
    (5.60340, -0.18660),
]
# Achimota, roughly 8 km away — must never join the Circle incident.
ACHIMOTA = (5.61980, -0.22690)


@pytest.fixture
async def db():
    settings = get_settings()
    engine = create_async_engine(settings.sqlalchemy_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


@pytest.fixture
async def reporter(db):
    """A throwaway account, removed with everything it created."""
    marker = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        email=f"itest-{marker}@nkwanta.test",
        password_hash=hash_password("integration-test-only"),
        display_name=f"Integration {marker}",
        role=UserRole.COMMUTER,
        reputation=0.5,
    )
    async with db() as session:
        session.add(user)
        await session.commit()

    yield user

    async with db() as session:
        report_ids = list(
            await session.scalars(select(Report.id).where(Report.reporter_id == user.id))
        )
        if report_ids:
            incident_ids = list(
                await session.scalars(
                    select(IncidentReport.incident_id).where(
                        IncidentReport.report_id.in_(report_ids)
                    )
                )
            )
            if incident_ids:
                await session.execute(
                    delete(Incident).where(Incident.id.in_(set(incident_ids)))
                )
            await session.execute(
                delete(OutboxMessage).where(OutboxMessage.aggregate_id.in_(report_ids))
            )
            await session.execute(delete(Report).where(Report.id.in_(report_ids)))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def _submit(db, reporter: User, lat: float, lon: float, minutes_ago: int = 0) -> Report:
    async with db() as session:
        user = await session.get(User, reporter.id)
        result = await submit_report(
            session,
            user,
            ReportCreate(
                incident_type=IncidentType.ACCIDENT,
                latitude=lat,
                longitude=lon,
                occurred_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago),
            ),
        )
        return result.report


async def _incidents_for(db, report_ids: list[uuid.UUID]) -> list[Incident]:
    async with db() as session:
        incident_ids = set(
            await session.scalars(
                select(IncidentReport.incident_id).where(
                    IncidentReport.report_id.in_(report_ids)
                )
            )
        )
        if not incident_ids:
            return []
        return list(
            await session.scalars(select(Incident).where(Incident.id.in_(incident_ids)))
        )


# =============================================================================


@pytest.mark.asyncio
async def test_postgis_is_actually_installed(db) -> None:
    from sqlalchemy import text

    async with db() as session:
        version = await session.scalar(text("SELECT postgis_version()"))
    assert version is not None


@pytest.mark.asyncio
async def test_submitting_a_report_writes_an_outbox_row_in_the_same_transaction(
    db, reporter
) -> None:
    """The report and its outbox row are committed together.

    **This test used to assert `processed_at is None`, and that was a mistake.** It
    passed in isolation and failed the moment the system was actually running: a worker
    — the local development server, or the deployed instance, both pointing at the same
    Neon database (TD-18) — drained the row within two seconds of it being written.

    The property being tested is that the row *exists* and belongs to this report.
    Whether it has been processed yet is somebody else's business, and asserting it made
    this test depend on nothing else being alive. A test that only passes when the system
    is switched off is testing the wrong thing.
    """
    report = await _submit(db, reporter, *CIRCLE[0])

    async with db() as session:
        msg = await session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id == report.id)
        )

    assert msg is not None, "no outbox row was written alongside the report"
    assert msg.aggregate_type == "report"
    assert msg.event_type == "report.submitted"
    assert msg.idempotency_key == f"report.submitted:{report.id}"
    assert msg.payload["report_id"] == str(report.id)
    # Never retried into failure, whoever processed it.
    assert msg.attempts == 0
    assert msg.last_error is None


@pytest.mark.asyncio
async def test_three_nearby_reports_become_one_incident(db, reporter) -> None:
    """The whole pipeline, for real: three reports at Circle, one incident out."""
    reports = [await _submit(db, reporter, lat, lon) for lat, lon in CIRCLE]

    worker = OutboxWorker(db, get_settings())
    for _ in range(4):                 # one pass per report, plus slack
        if await worker.drain_once() == 0:
            break

    incidents = await _incidents_for(db, [r.id for r in reports])

    assert len(incidents) == 1, f"expected one incident, got {len(incidents)}"
    incident = incidents[0]
    assert incident.report_count == 3
    assert incident.incident_type == IncidentType.ACCIDENT
    # Three fresh reports from one reputation-0.5 account: about 0.535
    assert incident.confidence >= THRESHOLD_CORROBORATED


@pytest.mark.asyncio
async def test_a_distant_report_forms_its_own_incident(db, reporter) -> None:
    """8 km apart must never merge — proves ST_DWithin is measuring metres, which is
    the thing that silently breaks if a geometry column is used instead of geography."""
    near = await _submit(db, reporter, *CIRCLE[0])
    far = await _submit(db, reporter, *ACHIMOTA)

    worker = OutboxWorker(db, get_settings())
    for _ in range(3):
        if await worker.drain_once() == 0:
            break

    incidents = await _incidents_for(db, [near.id, far.id])
    assert len(incidents) == 2


@pytest.mark.asyncio
async def test_coordinates_survive_the_round_trip(db, reporter) -> None:
    """Latitude and longitude come back as they went in. If they were swapped on the
    way into the geography column, this incident's centroid lands in the Gulf of
    Guinea and nothing else would have noticed."""
    from geoalchemy2.shape import to_shape

    report = await _submit(db, reporter, *CIRCLE[0])

    worker = OutboxWorker(db, get_settings())
    await worker.drain_once()

    incidents = await _incidents_for(db, [report.id])
    assert len(incidents) == 1

    point = to_shape(incidents[0].centroid)
    assert point.y == pytest.approx(CIRCLE[0][0], abs=1e-4)   # latitude
    assert point.x == pytest.approx(CIRCLE[0][1], abs=1e-4)   # longitude


@pytest.mark.asyncio
async def test_the_outbox_row_is_marked_processed(db, reporter) -> None:
    """Whoever drains it — this worker, or one already running — the row ends up marked.

    Safe to assert in either direction because the outcome is the same: the point of
    `FOR UPDATE SKIP LOCKED` is that two workers processing the same queue reach one
    answer rather than fighting over it.
    """
    report = await _submit(db, reporter, *CIRCLE[0])

    worker = OutboxWorker(db, get_settings())
    for _ in range(3):
        await worker.drain_once()
        async with db() as session:
            msg = await session.scalar(
                select(OutboxMessage).where(OutboxMessage.aggregate_id == report.id)
            )
        if msg.processed_at is not None:
            break

    assert msg.processed_at is not None
    assert msg.last_error is None


@pytest.mark.asyncio
async def test_draining_twice_does_not_duplicate_incidents(db, reporter) -> None:
    """Idempotence end to end. A restart mid-batch must not double-count."""
    reports = [await _submit(db, reporter, lat, lon) for lat, lon in CIRCLE[:2]]

    worker = OutboxWorker(db, get_settings())
    for _ in range(3):
        if await worker.drain_once() == 0:
            break

    first = await _incidents_for(db, [r.id for r in reports])
    await worker.drain_once()
    second = await _incidents_for(db, [r.id for r in reports])

    assert len(first) == len(second) == 1
    assert first[0].report_count == second[0].report_count


@pytest.mark.asyncio
async def test_demo_cleanup_removes_reports_it_did_not_seed(db) -> None:
    """A regression test for a bug found by running the thing.

    `clear_demo_data` used to delete only the reports it had seeded, assuming that was
    everything a demo account could own. The moment anyone used the application as
    `commuter@nkwanta.demo`, that account had reports with random ids — and
    `reports.reporter_id` is ON DELETE RESTRICT, so deleting the user was refused.

    The RESTRICT is correct: deleting a user must never silently erase the reports that
    justified sending a warden somewhere. The cleanup had to change instead.
    """
    from app.services.seed import SEED_USERS, _id, clear_demo_data, seed

    commuter_id = _id("user", "commuter")

    try:
        async with db() as session:
            await seed(session)

        # A report filed the way a person files one: no seed id, no seed idempotency key.
        async with db() as session:
            user = await session.get(User, commuter_id)
            assert user is not None, "seed did not create the demo commuter"
            await submit_report(
                session,
                user,
                ReportCreate(
                    incident_type=IncidentType.SURFACE_DEFECT,
                    latitude=CIRCLE[0][0],
                    longitude=CIRCLE[0][1],
                    occurred_at=dt.datetime.now(dt.timezone.utc),
                ),
            )

        # Must not raise a RestrictViolationError.
        async with db() as session:
            await clear_demo_data(session)

        async with db() as session:
            remaining_users = list(
                await session.scalars(
                    select(User.id).where(User.id.in_([_id("user", u.key) for u in SEED_USERS]))
                )
            )
            orphan_reports = list(
                await session.scalars(select(Report.id).where(Report.reporter_id == commuter_id))
            )

        assert remaining_users == []
        assert orphan_reports == []

    finally:
        # PUT THE DEMONSTRATION DATA BACK.
        #
        # This test proves that clearing works, which means its natural end state is a
        # database with no demonstration accounts in it. On a machine where tests and the
        # running application share one database (TD-18) that is destructive: it deleted
        # every demo account mid-session, and the next attempt to sign in as
        # commuter@nkwanta.demo failed with a 401 that looked like a bug in
        # authentication.
        #
        # A test that mutates shared state has to restore it. Reseeding here is not
        # tidiness — it is the difference between a test suite you can run at any time
        # and one that quietly breaks your demonstration.
        async with db() as session:
            await seed(session)


@pytest.mark.asyncio
async def test_a_later_report_merges_into_the_existing_incident(db, reporter) -> None:
    """The case incremental assignment cannot handle: an incident must grow when a new
    report arrives near it, not spawn a second one beside it."""
    first = await _submit(db, reporter, *CIRCLE[0])

    worker = OutboxWorker(db, get_settings())
    await worker.drain_once()
    assert (await _incidents_for(db, [first.id]))[0].report_count == 1

    second = await _submit(db, reporter, *CIRCLE[1])
    await worker.drain_once()

    incidents = await _incidents_for(db, [first.id, second.id])
    assert len(incidents) == 1
    assert incidents[0].report_count == 2
