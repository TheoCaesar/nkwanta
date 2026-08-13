"""Report intake — the most important twenty lines in the project.

Everything the advanced concept claims rests on one property of `submit_report`:

    The report and its outbox row are written in a SINGLE database transaction.

Get that wrong and the system can accept a report that nobody is ever warned about,
with no error anywhere and no way to find out. For an application whose entire purpose
is warning people, that failure destroys the product while looking perfectly healthy.

The naive version everyone writes first:

    save the report            <-- succeeds
    ...crash...
    send the notifications     <-- never happens

The gap between those two lines is the bug. There is no way to make it small enough to
be safe, because "small" is not "impossible". The fix is not a smaller gap — it is no
gap: put both writes in one transaction, so the database guarantees both or neither.

What the notifications need is then a durable instruction sitting in a table, picked up
by a worker afterwards. That table is the outbox.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.geo import CoordinateError, is_within_ghana, to_wkt_point
from app.models import OutboxMessage, Report, User
from app.schemas import ReportCreate

# A report claiming to be from the future is a broken client clock or a lie. A little
# slack absorbs ordinary clock drift between a phone and the server.
FUTURE_TOLERANCE = dt.timedelta(minutes=2)

# Older than this and it is history, not traffic information. It would also pollute
# clustering, which assumes reports arrive near the time they describe.
MAX_REPORT_AGE = dt.timedelta(hours=24)

EVENT_REPORT_SUBMITTED = "report.submitted"


class ReportRejected(ValueError):
    """The report is not acceptable. The message is safe to show a user."""


@dataclass(frozen=True)
class IntakeResult:
    report: Report
    duplicate: bool


def _validate(body: ReportCreate, now: dt.datetime) -> dt.datetime:
    """Everything that can be decided without touching the database."""
    try:
        to_wkt_point(body.latitude, body.longitude)
    except CoordinateError as exc:
        raise ReportRejected(str(exc)) from exc

    if not is_within_ghana(body.latitude, body.longitude):
        raise ReportRejected(
            "That location is outside Ghana. Check the coordinates are the right way "
            "round — latitude first, longitude second."
        )

    occurred_at = body.occurred_at or now
    if occurred_at.tzinfo is None:
        # Naive timestamps are ambiguous. Assume UTC rather than guess a local zone.
        occurred_at = occurred_at.replace(tzinfo=dt.timezone.utc)

    if occurred_at > now + FUTURE_TOLERANCE:
        raise ReportRejected("A report cannot describe something that has not happened yet.")
    if occurred_at < now - MAX_REPORT_AGE:
        raise ReportRejected("That is more than 24 hours ago. Report current conditions only.")

    return occurred_at


def build_outbox_message(report: Report, latitude: float, longitude: float) -> OutboxMessage:
    """The durable instruction: "this report arrived, act on it."

    The idempotency key is derived from the report id rather than randomly generated.
    That makes it deterministic: replaying intake for the same report produces the same
    key, so it can never enqueue the same work twice.
    """
    return OutboxMessage(
        aggregate_type="report",
        aggregate_id=report.id,
        event_type=EVENT_REPORT_SUBMITTED,
        payload={
            "report_id": str(report.id),
            "reporter_id": str(report.reporter_id),
            "incident_type": report.incident_type.value,
            "latitude": latitude,
            "longitude": longitude,
            "occurred_at": report.occurred_at.isoformat(),
        },
        idempotency_key=f"{EVENT_REPORT_SUBMITTED}:{report.id}",
    )


async def submit_report(
    session: AsyncSession,
    reporter: User,
    body: ReportCreate,
    *,
    now: dt.datetime | None = None,
) -> IntakeResult:
    now = now or dt.datetime.now(dt.timezone.utc)
    occurred_at = _validate(body, now)

    # Fast path for a retry we have already seen. Not the real defence — see below.
    if body.idempotency_key:
        existing = await session.scalar(
            select(Report).where(Report.idempotency_key == body.idempotency_key)
        )
        if existing is not None:
            return IntakeResult(report=existing, duplicate=True)

    report = Report(
        id=uuid.uuid4(),
        reporter_id=reporter.id,
        incident_type=body.incident_type,
        location=to_wkt_point(body.latitude, body.longitude),
        occurred_at=occurred_at,
        note=(body.note or None),
        idempotency_key=body.idempotency_key,
    )
    session.add(report)

    # ---------------------------------------------------------------------------
    # THE CRITICAL SECTION.
    #
    # Both rows are added to the same session and committed by a single commit()
    # below. PostgreSQL then guarantees both are durable or neither is. There is no
    # instant at which the report exists and the instruction to act on it does not.
    #
    # Do not move the commit. Do not add a commit between these two adds. Do not
    # "optimise" by writing the outbox row from the worker instead — the worker only
    # runs because this row exists.
    # ---------------------------------------------------------------------------
    session.add(build_outbox_message(report, body.latitude, body.longitude))

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # The real defence against duplicates. Two concurrent retries both pass the
        # SELECT above, both build a report, and the unique constraint fails one of
        # them. That is correct and expected: recover by returning the row the other
        # request committed.
        if body.idempotency_key:
            existing = await session.scalar(
                select(Report).where(Report.idempotency_key == body.idempotency_key)
            )
            if existing is not None:
                return IntakeResult(report=existing, duplicate=True)
        raise

    await session.refresh(report)
    return IntakeResult(report=report, duplicate=False)
