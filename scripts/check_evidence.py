"""Say what is actually attached to the most recent reports.

    python -m scripts.check_evidence
    python -m scripts.check_evidence commuter@nkwanta.demo

Written because a missing attachment has two very different causes that look identical
from the interface:

  * **the upload never succeeded** — there is no row, and the reason was a 422 the page
    used to swallow; or
  * **the upload succeeded and the viewer is not allowed to see it** — the row is there
    and `may_play` filtered it out of the response.

The first is a bug to fix. The second is the privacy rule working. This script reads the
database directly and says which, so nobody has to guess from a blank space.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Attachment, AttachmentKind, Report, User

LIMIT = 15


async def main(email: str | None) -> int:
    settings = get_settings()
    if not settings.database_configured:
        print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        return 1

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        query = (
            select(Report, User)
            .join(User, User.id == Report.reporter_id)
            .order_by(desc(Report.occurred_at))
            .limit(LIMIT)
        )
        if email:
            query = query.where(User.email == email.lower())

        rows = (await session.execute(query)).all()
        if not rows:
            print("No reports found." + (f" (filtered to {email})" if email else ""))
            await engine.dispose()
            return 0

        report_ids = [r.id for r, _ in rows]
        attachments: dict = {}
        for a in await session.scalars(
            select(Attachment).where(Attachment.report_id.in_(report_ids))
        ):
            attachments.setdefault(a.report_id, []).append(a)

        print(f"{'when':<20} {'reporter':<18} {'type':<15} evidence")
        print("-" * 88)
        voice_count = 0
        for report, user in rows:
            items = attachments.get(report.id, [])
            voice_count += sum(1 for a in items if a.kind is AttachmentKind.VOICE)
            if items:
                described = ", ".join(
                    f"{a.kind.value} {a.byte_size // 1024}KB "
                    f"{'shared' if a.is_public else 'PRIVATE'}"
                    for a in items
                )
            else:
                described = "— nothing attached —"
            note = " +note" if report.note else ""
            print(
                f"{report.occurred_at:%Y-%m-%d %H:%M}    "
                f"{user.display_name[:17]:<18} {report.incident_type.value:<15} "
                f"{described}{note}"
            )

        print()
        if voice_count == 0:
            print(
                "No voice attachments exist on any of these reports.\n"
                "So the recording never reached the database — this is an upload failure,\n"
                "not a visibility rule. Submit again with the browser's Network tab open\n"
                "and read the response to POST /reports/{id}/voice; it says why in words."
            )
        else:
            print(
                f"{voice_count} voice attachment(s) exist.\n"
                "A PRIVATE one is invisible to other commuters by design, but its own\n"
                "reporter and any officer or warden can always play it. If the reporter\n"
                "cannot see their own, that is a bug — check they are signed in as the\n"
                "account that filed the report."
            )

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
