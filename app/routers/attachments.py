"""Uploading and playing back recorded evidence.

Two things here are security decisions rather than plumbing, and both are worth
volunteering in a viva.

**Serving user-uploaded bytes is dangerous.** A browser that decides for itself what a
file contains can be tricked into running an upload as HTML — someone uploads a file
declared as audio, a browser sniffs it, sees markup, and executes it on your origin. The
response headers below stop that: an explicit content type, `nosniff` so the browser does
not overrule it, and `Content-Disposition: attachment` so nothing renders inline.

**A voice note identifies the person who recorded it.** That is not a normal attachment —
it is close to biometric. NFR-4 says a reported party is never exposed to other users, and
a recording of someone's voice is exactly the kind of thing that would expose them. So
playback is restricted to the person who recorded it and to the control room. A commuter
browsing the map never hears another commuter.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, OptionalUser
from app.db import get_session
from app.models import Attachment, AttachmentKind, Report, UserRole
from app.schemas import AttachmentResponse, VisibilityRequest
from app.services import attachments as svc

router = APIRouter(tags=["attachments"])


def _to_response(a: Attachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=a.id,
        report_id=a.report_id,
        kind=a.kind,
        content_type=a.content_type,
        byte_size=a.byte_size,
        duration_seconds=a.duration_seconds,
        created_at=a.created_at,
        url=f"/attachments/{a.id}",
        is_public=a.is_public,
    )


@router.post(
    "/reports/{report_id}/voice",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a spoken report",
)
async def upload_voice(
    report_id: uuid.UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File(description="Audio clip, 512 KB maximum")],
    duration_seconds: Annotated[float | None, Form()] = None,
    share_publicly: Annotated[bool, Form(
        description="Let other commuters hear this. Off unless you say otherwise."
    )] = False,
) -> AttachmentResponse:
    """This is the answer to NFR-3.

    The driver-facing view is read-only and must never ask anyone to type while moving.
    Hold a button, speak, release — the report is filed and the recording attached.

    `share_publicly` is the reporter's own decision and defaults to off. A recording
    identifies its speaker, and only the speaker knows whether that matters: reporting a
    flood accuses nobody, reporting a named driver very much does. It can be changed
    afterwards — see PATCH /attachments/{id}/visibility.
    """
    data = await file.read()
    try:
        result = await svc.attach(
            session,
            report_id,
            user,
            AttachmentKind.VOICE,
            file.content_type or "",
            data,
            duration_seconds,
            is_public=share_publicly,
        )
    except svc.AttachmentRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return _to_response(result.attachment)


@router.post(
    "/reports/{report_id}/photo",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a photograph",
)
async def upload_photo(
    report_id: uuid.UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File(description="Image, 250 KB maximum")],
) -> AttachmentResponse:
    data = await file.read()
    try:
        result = await svc.attach(
            session, report_id, user, AttachmentKind.PHOTO, file.content_type or "", data
        )
    except svc.AttachmentRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return _to_response(result.attachment)


@router.get(
    "/attachments/{attachment_id}",
    summary="Play back or download an attachment",
    responses={200: {"content": {"audio/webm": {}, "image/jpeg": {}}}},
)
async def fetch_attachment(
    attachment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: OptionalUser = None,
) -> Response:
    """Playable if the reporter shared it, if it is yours, or if you are control room.

    A recording identifies its speaker, so the reporter decides whether other commuters
    hear it — and can change their mind. Officers and wardens can always play it,
    shared or not, because someone being sent to a junction should hear why.
    """
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attachment.")

    report = await session.get(Report, attachment.report_id)

    if not svc.may_play(attachment, report, user):
        # 404 rather than 403. A 403 would confirm the attachment exists, which is
        # itself information about someone else's report.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attachment.")

    return Response(
        content=attachment.data,
        media_type=attachment.content_type,
        headers={
            # Do not let the browser second-guess the type. Without this, a file
            # uploaded as audio but containing markup can be sniffed as HTML and
            # executed on our origin.
            "X-Content-Type-Options": "nosniff",
            # Never render inline, whatever it turns out to be.
            "Content-Disposition": f'attachment; filename="{attachment_id}"',
            # `private` on anything not shared, so a proxy cannot cache one person's
            # recording and serve it to the next caller.
            "Cache-Control": (
                "public, max-age=3600" if attachment.is_public else "private, max-age=3600"
            ),
        },
    )


@router.patch(
    "/attachments/{attachment_id}/visibility",
    response_model=AttachmentResponse,
    summary="Share your recording, or stop sharing it",
)
async def set_visibility(
    attachment_id: uuid.UUID,
    body: VisibilityRequest,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AttachmentResponse:
    """Only the person who recorded it may change this — not even an officer.

    Consent that somebody else can give on your behalf is not consent, and consent that
    cannot be withdrawn is not a choice.
    """
    try:
        attachment = await svc.set_visibility(session, attachment_id, user, body.is_public)
    except svc.AttachmentRejected as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _to_response(attachment)


@router.get(
    "/reports/{report_id}/attachments",
    response_model=list[AttachmentResponse],
    summary="What is attached to a report",
)
async def list_attachments(
    report_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: OptionalUser = None,
) -> list[AttachmentResponse]:
    """Lists only what the caller could actually play.

    Filtering the list with the same rule that guards the bytes means an unshared
    recording is not merely unplayable but invisible. Listing something and then
    refusing it announces that it exists.
    """
    from sqlalchemy import select

    report = await session.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such report.")

    rows = await session.scalars(
        select(Attachment)
        .where(Attachment.report_id == report_id)
        .order_by(Attachment.created_at)
    )
    visible = [a for a in rows if svc.may_play(a, report, user)]
    return [_to_response(a) for a in visible]
