"""Populate the database with demonstration data, then build the incidents.

    python -m scripts.seed_demo            # add demo data, keep anything already there
    python -m scripts.seed_demo --reset    # remove previous demo data first

Timestamps are relative to when this runs, so the map always looks current. Confidence
halves every 45 minutes — data seeded yesterday would be invisible today. **Run this
shortly before any demonstration or viva.**
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Incident, IncidentStatus, Report, User
from app.services.seed import DEMO_PASSWORD, clear_demo_data, seed
from app.worker import OutboxWorker


async def main(reset: bool) -> int:
    settings = get_settings()
    if not settings.database_configured:
        print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        return 1

    engine = create_async_engine(settings.sqlalchemy_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        if reset:
            async with maker() as session:
                print("removing previous demo data ...")
                await clear_demo_data(session)

        async with maker() as session:
            result = await seed(session)
        print(f"seeded  {result.users_created} accounts, {result.reports_created} reports, "
              f"{result.outbox_queued} queued for processing")

        # Drain through the same worker the live system uses. Seeded reports are not
        # special-cased anywhere — they go through clustering and confidence exactly
        # as a real submission would.
        print("building incidents ...")
        worker = OutboxWorker(maker, settings)
        passes = 0
        while passes < 20:
            handled = await worker.drain_once()
            passes += 1
            if handled == 0:
                break
        print(f"  {worker.processed_count} messages processed in {passes} passes, "
              f"{worker.failed_count} failed")

        async with maker() as session:
            users = await session.scalar(select(func.count()).select_from(User))
            reports = await session.scalar(select(func.count()).select_from(Report))
            incidents = (
                await session.scalars(
                    select(Incident).order_by(Incident.confidence.desc())
                )
            ).all()

        print()
        print(f"database now holds {users} accounts, {reports} reports, {len(incidents)} incidents")
        print()
        print(f"  {'incident':<18} {'reports':>7} {'confidence':>11}   status")
        print(f"  {'-'*18} {'-'*7} {'-'*11}   {'-'*12}")
        for inc in incidents[:14]:
            print(f"  {inc.incident_type.value:<18} {inc.report_count:>7} "
                  f"{inc.confidence:>11.3f}   {inc.status.value}")
        if len(incidents) > 14:
            print(f"  ... and {len(incidents) - 14} more")

        verified = sum(1 for i in incidents if i.status == IncidentStatus.VERIFIED)
        print()
        print(f"  {verified} incident(s) above the escalation threshold — these reach the "
              f"dispatch queue")
        print()
        print(f"sign in with any of:")
        print(f"  commuter@nkwanta.demo   warden@nkwanta.demo")
        print(f"  officer@nkwanta.demo    admin@nkwanta.demo")
        print(f"password: {DEMO_PASSWORD}")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true",
                        help="remove previously seeded demo data first")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.reset)))
