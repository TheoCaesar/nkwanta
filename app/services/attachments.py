"""Accepting recorded evidence.

The rules are all about not trusting the uploader. A file arriving over HTTP carries
three things a client controls completely — its bytes, its declared content type and its
filename — and none of them can be believed.


WHY VOICE EXISTS AT ALL
-----------------------
NFR-3 says the driver-facing view is passive and read-only, with no typing while
driving. Until now that was a constraint with no answer: the requirement said what the
system would not do without saying how a driver reports anything.

Hold a button, speak, release. That is the answer, and it happens to suit the user base
better than a keyboard does regardless of safety.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attachment, AttachmentKind, Report, User, UserRole

# 512 KB. Roughly 60 seconds of Opus at a bitrate suited to speech, which is more than
# anyone needs to say "tipper truck across two lanes at Circle". Also enforced by a
# CHECK constraint, so a future endpoint cannot forget it.
MAX_BYTES = 524_288

# 250 KB for images, which is generous after the client-side downscale.
MAX_PHOTO_BYTES = 256_000

# Allow-list, never a block-list. A block-list is a list of the attacks you thought of.
ALLOWED_AUDIO = {
    "audio/webm",      # what MediaRecorder produces in Chrome and Firefox
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/aac",
    "audio/wav",
    "audio/x-wav",
}

ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp"}

MAX_ATTACHMENTS_PER_REPORT = 4


class AttachmentRejected(ValueError):
    """The upload is not acceptable. The message is safe to show a user."""


@dataclass(frozen=True)
class UploadResult:
    attachment: Attachment
    report_id: uuid.UUID


def _limits(kind: AttachmentKind) -> tuple[set[str], int]:
    if kind is AttachmentKind.VOICE:
        return ALLOWED_AUDIO, MAX_BYTES
    return ALLOWED_IMAGE, MAX_PHOTO_BYTES


def validate(kind: AttachmentKind, content_type: str, data: bytes) -> None:
    """Everything that can be decided without touching the database."""
    allowed, max_bytes = _limits(kind)

    # Strip any parameters — browsers send things like "audio/webm;codecs=opus".
    declared = (content_type or "").split(";")[0].strip().lower()

    if declared not in allowed:
        raise AttachmentRejected(
            f"{declared or 'that file type'} is not accepted for a {kind.value}. "
            f"Allowed: {', '.join(sorted(allowed))}."
        )

    if not data:
        raise AttachmentRejected("The file is empty.")

    if len(data) > max_bytes:
        raise AttachmentRejected(
            f"That file is {len(data) // 1024} KB. The limit for a {kind.value} is "
            f"{max_bytes // 1024} KB — record a shorter clip or reduce the quality."
        )


def may_play(attachment: Attachment, report: Report | None, viewer: User | None) -> bool:
    """Who is allowed to hear or see the bytes.

    Three routes, and the order states the priority:

    1. **The reporter shared it.** They chose to, and may unchoose at any time.
    2. **It is their own.** You can always play back what you recorded.
    3. **Control room.** Officers, wardens and admins need it to act on the incident,
       shared or not — a warden being sent somewhere should hear why.

    Everyone else gets nothing, and gets it as a 404 rather than a 403, because a 403
    confirms the attachment exists and that is itself information about someone else's
    report.
    """
    if attachment.is_public:
        return True
    if viewer is None:
        return False
    if report is not None and report.reporter_id == viewer.id:
        return True
    return viewer.role in {UserRole.OFFICER, UserRole.WARDEN, UserRole.ADMIN}


async def set_visibility(
    session: AsyncSession, attachment_id: uuid.UUID, owner: User, is_public: bool
) -> Attachment:
    """Give or withdraw consent. Only the person who recorded it may do either.

    Not even an officer can publish someone's voice on their behalf. The point of asking
    is lost if anybody else can answer.
    """
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None:
        raise AttachmentRejected("No such attachment.")

    report = await session.get(Report, attachment.report_id)
    if report is None or report.reporter_id != owner.id:
        raise AttachmentRejected("Only the person who recorded this can change who hears it.")

    attachment.is_public = is_public
    await session.commit()
    await session.refresh(attachment)
    return attachment


async def attach(
    session: AsyncSession,
    report_id: uuid.UUID,
    uploader: User,
    kind: AttachmentKind,
    content_type: str,
    data: bytes,
    duration_seconds: float | None = None,
    is_public: bool = False,
) -> UploadResult:
    """Attach evidence to a report.

    Only the person who filed the report may add to it. Reports are immutable records of
    what someone said; letting a third party bolt evidence onto someone else's statement
    would make the record mean something different from what its author asserted.
    """
    validate(kind, content_type, data)

    report = await session.get(Report, report_id)
    if report is None:
        raise AttachmentRejected("No such report.")

    if report.reporter_id != uploader.id:
        raise AttachmentRejected("You can only attach evidence to your own report.")

    existing = await session.scalar(
        select(func.count())
        .select_from(Attachment)
        .where(Attachment.report_id == report_id)
    )
    if (existing or 0) >= MAX_ATTACHMENTS_PER_REPORT:
        raise AttachmentRejected(
            f"A report may carry at most {MAX_ATTACHMENTS_PER_REPORT} attachments."
        )

    if kind is AttachmentKind.VOICE:
        already_voice = await session.scalar(
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.report_id == report_id, Attachment.kind == kind)
        )
        if already_voice:
            raise AttachmentRejected("This report already has a voice note.")

    attachment = Attachment(
        id=uuid.uuid4(),
        report_id=report_id,
        kind=kind,
        content_type=content_type.split(";")[0].strip().lower(),
        byte_size=len(data),
        duration_seconds=duration_seconds,
        data=data,
        # Defaults to False. Consent is given, never assumed — a client that forgets to
        # send the field has not consented.
        is_public=is_public,
    )
    session.add(attachment)
    await session.commit()
    await session.refresh(attachment)
    return UploadResult(attachment=attachment, report_id=report_id)


async def report_ids_with_evidence(
    session: AsyncSession, report_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of these reports carry recorded evidence.

    Used by the projector to weight them slightly higher. One query for the whole
    neighbourhood rather than one per report.
    """
    if not report_ids:
        return set()
    rows = await session.scalars(
        select(Attachment.report_id).where(Attachment.report_id.in_(report_ids)).distinct()
    )
    return set(rows)
