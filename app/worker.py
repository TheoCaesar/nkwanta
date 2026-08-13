"""The outbox worker — the other half of the transactional outbox.

`submit_report` writes a report and an outbox row in one transaction, so the instruction
to act can never be lost. This is what picks that instruction up and acts on it.

It runs **in-process**, as an asyncio task inside the API service, rather than as a
separate worker. That is a compromise forced by Render's free tier permitting a single
service, and it is recorded as technical debt TD-01 with its real costs — it cannot be
scaled independently, and it dies whenever the API restarts. The code is deliberately
written as a self-contained class with no dependency on FastAPI's request context, so
extracting it later is a move rather than a rewrite.


THE LOOP
--------
    every POLL_SECONDS:
        claim a batch of unprocessed rows
        for each: run its handler, mark processed
        commit

The claim uses ``FOR UPDATE SKIP LOCKED``. With one worker that changes nothing; with
several it is what stops two of them grabbing the same row. Writing it correctly now
costs nothing and means the extraction in TD-01 does not need a rethink.


WHY A RETRY CANNOT DOUBLE-SEND
------------------------------
Delivery is at-least-once: if a gateway does not answer we cannot tell whether the
message went out, so we send again. Every outbox row carries a unique idempotency key,
and the sink records which keys it has already handled. Send five times, the recipient
hears once.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.models import OutboxMessage
from app.services.projection import rebuild_for_report
from app.services.reports import EVENT_REPORT_SUBMITTED

log = logging.getLogger("nkwanta.worker")

POLL_SECONDS = 2.0
BATCH_SIZE = 20

# After this many failures a row is left alone. It stays in the table, unprocessed and
# visible, rather than being deleted or retried forever. That is a dead letter queue in
# the crudest possible form — TD-06 covers the real one.
MAX_ATTEMPTS = 5

Handler = Callable[[AsyncSession, OutboxMessage, Settings], Awaitable[None]]


async def handle_report_submitted(
    session: AsyncSession, message: OutboxMessage, settings: Settings
) -> None:
    """A report arrived. Recompute the incidents it could have affected."""
    outcome = await rebuild_for_report(session, message.aggregate_id, settings)
    log.info(
        "rebuilt from report %s: %d reports considered, %d incidents removed, %d written",
        message.aggregate_id,
        outcome.reports_considered,
        outcome.incidents_removed,
        outcome.incidents_written,
    )


HANDLERS: dict[str, Handler] = {
    EVENT_REPORT_SUBMITTED: handle_report_submitted,
}


class OutboxWorker:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings or get_settings()
        self._poll_seconds = poll_seconds
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self.processed_count = 0
        self.failed_count = 0

    # --- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="outbox-worker")
        log.info("outbox worker started, polling every %.1fs", self._poll_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log.info("outbox worker stopped after %d processed, %d failed",
                 self.processed_count, self.failed_count)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                handled = await self.drain_once()
                # Nothing waiting? Sleep. Work waiting? Go straight round again, so a
                # burst of reports is cleared quickly rather than at one batch per tick.
                if handled == 0:
                    await asyncio.sleep(self._poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad pass must never kill the loop. If it did, every notification
                # after it would be silently lost — the exact failure the outbox exists
                # to prevent.
                log.exception("outbox worker pass failed; continuing")
                await asyncio.sleep(self._poll_seconds)

    # --- the work -------------------------------------------------------------

    async def drain_once(self) -> int:
        """Process one batch. Returns how many rows were handled.

        Exposed publicly so tests and the admin endpoint can drive it directly, rather
        than sleeping and hoping the background loop got there.
        """
        handled = 0
        async with self._sessionmaker() as session:
            messages = await self._claim(session)
            for message in messages:
                try:
                    handler = HANDLERS.get(message.event_type)
                    if handler is None:
                        # Unknown event types are marked processed, not retried. A row
                        # nothing can handle will never succeed, and leaving it would
                        # block the queue behind it forever.
                        log.warning("no handler for %s, skipping", message.event_type)
                        message.processed_at = dt.datetime.now(dt.timezone.utc)
                    else:
                        await handler(session, message, self._settings)
                        message.processed_at = dt.datetime.now(dt.timezone.utc)
                        message.last_error = None
                        self.processed_count += 1
                    handled += 1
                except Exception as exc:  # noqa: BLE001 — record and move on
                    message.attempts += 1
                    message.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                    self.failed_count += 1
                    log.exception("outbox row %s failed (attempt %d)", message.id, message.attempts)

            if messages:
                # One commit for the batch: the work and the "processed" marks land
                # together, so a crash mid-batch replays the whole batch rather than
                # leaving some rows marked done with their effects missing.
                await session.commit()

        return handled

    async def _claim(self, session: AsyncSession) -> list[OutboxMessage]:
        result = await session.scalars(
            select(OutboxMessage)
            .where(
                OutboxMessage.processed_at.is_(None),
                OutboxMessage.attempts < MAX_ATTEMPTS,
            )
            .order_by(OutboxMessage.created_at)
            .limit(BATCH_SIZE)
            # SKIP LOCKED: rows another worker holds are stepped over rather than
            # waited on. With one worker it is a no-op; with several it is what makes
            # the queue safe.
            .with_for_update(skip_locked=True)
        )
        return list(result)


# Module-level handle so the lifespan can start and stop it, and so an admin endpoint
# can trigger a drain on demand during a demonstration.
worker: OutboxWorker | None = None


def get_worker() -> OutboxWorker | None:
    return worker


def set_worker(w: OutboxWorker | None) -> None:
    global worker
    worker = w
