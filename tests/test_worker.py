"""B09 — outbox worker semantics.

The worker is the half of the transactional outbox that acts. Intake guarantees the
instruction is never lost; this guarantees it is eventually carried out, exactly once,
and that no single bad row can stop everything behind it.

These use a stubbed session so they run without PostgreSQL. What is being tested is the
worker's *decision-making* — what it claims, what it marks, what it does when a handler
throws — not SQLAlchemy's ability to execute a query.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

import pytest

from app.config import get_settings
from app.models import OutboxMessage
from app.worker import MAX_ATTEMPTS, HANDLERS, OutboxWorker
from app.services.reports import EVENT_REPORT_SUBMITTED


def _message(event_type: str = EVENT_REPORT_SUBMITTED, attempts: int = 0) -> OutboxMessage:
    return OutboxMessage(
        id=uuid.uuid4(),
        aggregate_type="report",
        aggregate_id=uuid.uuid4(),
        event_type=event_type,
        payload={},
        idempotency_key=f"{event_type}:{uuid.uuid4()}",
        attempts=attempts,
    )


class FakeSession:
    def __init__(self, messages: list[OutboxMessage]) -> None:
        self._messages = messages
        self.commits = 0

    async def scalars(self, _stmt):
        # The real query filters on processed_at and attempts; mirror that here so the
        # tests exercise the same selection rules.
        return [
            m for m in self._messages
            if m.processed_at is None and m.attempts < MAX_ATTEMPTS
        ]

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _sessionmaker(messages: list[OutboxMessage]):
    session = FakeSession(messages)

    def factory():
        return session

    factory.session = session  # type: ignore[attr-defined]
    return factory


@pytest.fixture(autouse=True)
def _restore_handlers():
    original = dict(HANDLERS)
    yield
    HANDLERS.clear()
    HANDLERS.update(original)


# =============================================================================
# THE HAPPY PATH
# =============================================================================


@pytest.mark.asyncio
async def test_a_pending_row_is_handled_and_marked_processed() -> None:
    seen = []

    async def handler(session, message, settings):
        seen.append(message.id)

    HANDLERS[EVENT_REPORT_SUBMITTED] = handler
    msg = _message()
    factory = _sessionmaker([msg])

    worker = OutboxWorker(factory, get_settings())
    handled = await worker.drain_once()

    assert handled == 1
    assert seen == [msg.id]
    assert msg.processed_at is not None
    assert worker.processed_count == 1


@pytest.mark.asyncio
async def test_an_already_processed_row_is_not_handled_again() -> None:
    """Idempotence at the queue level. Without it a restart mid-batch would redo work."""
    calls = []

    async def handler(session, message, settings):
        calls.append(message.id)

    HANDLERS[EVENT_REPORT_SUBMITTED] = handler
    msg = _message()
    msg.processed_at = dt.datetime.now(dt.timezone.utc)

    worker = OutboxWorker(_sessionmaker([msg]), get_settings())
    assert await worker.drain_once() == 0
    assert calls == []


@pytest.mark.asyncio
async def test_the_batch_commits_once_not_per_row() -> None:
    """One commit for the batch means a crash replays the whole batch, rather than
    leaving some rows marked done with their effects missing."""
    async def handler(session, message, settings):
        return None

    HANDLERS[EVENT_REPORT_SUBMITTED] = handler
    factory = _sessionmaker([_message() for _ in range(5)])

    worker = OutboxWorker(factory, get_settings())
    await worker.drain_once()

    assert factory.session.commits == 1


# =============================================================================
# FAILURE HANDLING
# =============================================================================


@pytest.mark.asyncio
async def test_a_failing_row_records_the_error_and_is_not_marked_processed() -> None:
    async def handler(session, message, settings):
        raise RuntimeError("gateway unreachable")

    HANDLERS[EVENT_REPORT_SUBMITTED] = handler
    msg = _message()

    worker = OutboxWorker(_sessionmaker([msg]), get_settings())
    await worker.drain_once()

    assert msg.processed_at is None
    assert msg.attempts == 1
    assert "gateway unreachable" in msg.last_error
    assert worker.failed_count == 1


@pytest.mark.asyncio
async def test_one_bad_row_does_not_block_the_rest_of_the_batch() -> None:
    """Head-of-line blocking would mean a single poison message silently stops every
    warning behind it — the exact failure the outbox exists to prevent."""
    good_a, bad, good_b = _message(), _message(), _message()

    async def handler(session, message, settings):
        if message.id == bad.id:
            raise ValueError("poison")

    HANDLERS[EVENT_REPORT_SUBMITTED] = handler
    worker = OutboxWorker(_sessionmaker([good_a, bad, good_b]), get_settings())
    await worker.drain_once()

    assert good_a.processed_at is not None
    assert good_b.processed_at is not None
    assert bad.processed_at is None


@pytest.mark.asyncio
async def test_a_row_is_abandoned_after_the_attempt_limit() -> None:
    """The crudest possible dead letter queue: the row stays in the table, unprocessed
    and visible, instead of being deleted or retried forever. TD-06 covers the real one."""
    async def handler(session, message, settings):
        raise RuntimeError("still broken")

    HANDLERS[EVENT_REPORT_SUBMITTED] = handler
    exhausted = _message(attempts=MAX_ATTEMPTS)

    worker = OutboxWorker(_sessionmaker([exhausted]), get_settings())
    assert await worker.drain_once() == 0
    assert exhausted.attempts == MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_an_unknown_event_type_is_skipped_not_retried() -> None:
    """A row nothing can handle will never succeed. Retrying it forever would hold up
    everything behind it."""
    msg = _message(event_type="something.we.removed")

    worker = OutboxWorker(_sessionmaker([msg]), get_settings())
    handled = await worker.drain_once()

    assert handled == 1
    assert msg.processed_at is not None
    assert msg.attempts == 0


# =============================================================================
# THE LOOP
# =============================================================================


@pytest.mark.asyncio
async def test_start_and_stop_are_clean() -> None:
    worker = OutboxWorker(_sessionmaker([]), get_settings(), poll_seconds=0.01)
    worker.start()
    await asyncio.sleep(0.05)
    await worker.stop()
    assert worker._task is None


@pytest.mark.asyncio
async def test_starting_twice_does_not_create_a_second_loop() -> None:
    worker = OutboxWorker(_sessionmaker([]), get_settings(), poll_seconds=0.01)
    worker.start()
    first = worker._task
    worker.start()
    assert worker._task is first
    await worker.stop()


@pytest.mark.asyncio
async def test_a_handler_exception_does_not_kill_the_loop() -> None:
    """If one bad pass could stop the loop, every notification after it would be lost
    silently — with no error and no way to notice."""
    async def handler(session, message, settings):
        raise RuntimeError("boom")

    HANDLERS[EVENT_REPORT_SUBMITTED] = handler
    worker = OutboxWorker(_sessionmaker([_message()]), get_settings(), poll_seconds=0.01)
    worker.start()
    await asyncio.sleep(0.06)
    still_running = worker._task is not None and not worker._task.done()
    await worker.stop()

    assert still_running


def test_report_submitted_has_a_registered_handler() -> None:
    assert EVENT_REPORT_SUBMITTED in HANDLERS
