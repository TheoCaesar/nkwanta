"""F — voice notes and photographs.

Two groups, and the second matters more than it first appears.

    VALIDATION -- nothing a client sends can be believed
    PRIVACY    -- a voice note identifies the person who recorded it

A recording of someone's voice is close to biometric data. NFR-4 says a reported party is
never exposed to other users, and audio is exactly the sort of thing that would expose
them, so playback is restricted to the recorder and the control room.
"""

from __future__ import annotations

import inspect
import uuid

import jwt
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app import media_tokens

from app.confidence import (
    DEFAULT_EVIDENCE_STRENGTH,
    EVIDENCE_BONUS,
    THRESHOLD_VERIFIED,
    report_weight,
)
from app.models import Attachment, AttachmentKind, IncidentType, Report, User, UserRole
from app.routers.attachments import attachment_url, fetch_attachment, upload_photo, upload_voice
from app.security import create_access_token, decode_access_token
from app.services.attachments import (
    ALLOWED_AUDIO,
    ALLOWED_IMAGE,
    MAX_BYTES,
    MAX_PHOTO_BYTES,
    AttachmentRejected,
    may_play,
    validate,
)

VALID_AUDIO = b"\x1a\x45\xdf\xa3" + b"\x00" * 2048       # webm-ish header, plausible size
VALID_IMAGE = b"\xff\xd8\xff\xe0" + b"\x00" * 2048       # jpeg magic


def _constraints() -> set[str]:
    return {c.name for c in Attachment.__table__.constraints if c.name}


# =============================================================================
# VALIDATION
# =============================================================================


@pytest.mark.parametrize("content_type", sorted(ALLOWED_AUDIO))
def test_accepted_audio_types(content_type: str) -> None:
    validate(AttachmentKind.VOICE, content_type, VALID_AUDIO)


def test_browser_codec_parameters_are_tolerated() -> None:
    """Chrome's MediaRecorder sends `audio/webm;codecs=opus`. Rejecting that would
    reject the only thing a browser actually produces."""
    validate(AttachmentKind.VOICE, "audio/webm;codecs=opus", VALID_AUDIO)


def test_content_type_matching_is_case_insensitive() -> None:
    validate(AttachmentKind.VOICE, "AUDIO/WEBM", VALID_AUDIO)


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "application/javascript", "application/octet-stream", "image/svg+xml", ""],
)
def test_dangerous_or_unknown_types_are_refused(content_type: str) -> None:
    """An allow-list, never a block-list. A block-list is a list of the attacks you
    happened to think of."""
    with pytest.raises(AttachmentRejected):
        validate(AttachmentKind.VOICE, content_type, VALID_AUDIO)


def test_an_image_is_not_acceptable_as_a_voice_note() -> None:
    with pytest.raises(AttachmentRejected):
        validate(AttachmentKind.VOICE, "image/jpeg", VALID_IMAGE)


def test_audio_is_not_acceptable_as_a_photograph() -> None:
    with pytest.raises(AttachmentRejected):
        validate(AttachmentKind.PHOTO, "audio/webm", VALID_AUDIO)


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(AttachmentRejected, match="empty"):
        validate(AttachmentKind.VOICE, "audio/webm", b"")


def test_oversized_audio_is_refused() -> None:
    with pytest.raises(AttachmentRejected, match="limit"):
        validate(AttachmentKind.VOICE, "audio/webm", b"\x00" * (MAX_BYTES + 1))


def test_audio_at_exactly_the_limit_is_accepted() -> None:
    """Off-by-one at a boundary is the classic way a size check goes wrong."""
    validate(AttachmentKind.VOICE, "audio/webm", b"\x00" * MAX_BYTES)


def test_photographs_have_a_tighter_limit_than_audio() -> None:
    assert MAX_PHOTO_BYTES < MAX_BYTES
    with pytest.raises(AttachmentRejected):
        validate(AttachmentKind.PHOTO, "image/jpeg", b"\x00" * (MAX_PHOTO_BYTES + 1))


def test_the_size_error_says_what_to_do_about_it() -> None:
    with pytest.raises(AttachmentRejected) as exc:
        validate(AttachmentKind.VOICE, "audio/webm", b"\x00" * (MAX_BYTES + 1))
    assert "shorter" in str(exc.value)


@given(size=st.integers(min_value=1, max_value=MAX_BYTES))
def test_any_size_within_the_limit_is_accepted(size: int) -> None:
    validate(AttachmentKind.VOICE, "audio/webm", b"\x00" * size)


# =============================================================================
# THE DATABASE ENFORCES THE LIMIT TOO
# =============================================================================


def test_the_size_cap_is_a_database_constraint_not_only_a_check() -> None:
    """A limit that lives only in the upload handler is one a future endpoint can
    forget. This one is in the schema."""
    assert "ck_attachments_size_limit" in _constraints()
    assert "ck_attachments_size_positive" in _constraints()


def test_attachments_are_removed_with_their_report() -> None:
    """CASCADE here, unlike reports themselves which survive user deletion under
    RESTRICT. An attachment has no meaning without the report it belongs to."""
    fk = next(iter(Attachment.__table__.columns["report_id"].foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_attachments_live_in_their_own_table() -> None:
    """Not columns on `reports`. That table is scanned constantly by clustering, and
    binary data in those rows would compete with the query workload for buffer cache —
    audio nobody is listening to would slow down every clustering pass."""
    from app.models import Report

    assert "attachments" in Attachment.__table__.name
    assert not any(
        c.name in {"voice_data", "photo_data", "audio"} for c in Report.__table__.columns
    )


def test_only_two_kinds_exist() -> None:
    assert {k.value for k in AttachmentKind} == {"voice", "photo"}


# =============================================================================
# CONSENT AND VISIBILITY
#
# A recording identifies its speaker, and the reporter is the only person who knows
# whether that matters — reporting a flood accuses nobody, reporting a named driver
# very much does. So they choose, and they can change their mind.
# =============================================================================


def _attachment(is_public: bool = False) -> Attachment:
    return Attachment(
        id=uuid.uuid4(),
        report_id=uuid.uuid4(),
        kind=AttachmentKind.VOICE,
        content_type="audio/webm",
        byte_size=1024,
        data=b"x" * 1024,
        is_public=is_public,
    )


def _report(reporter_id: uuid.UUID) -> Report:
    return Report(id=uuid.uuid4(), reporter_id=reporter_id, incident_type=IncidentType.ACCIDENT)


def _user(role: UserRole = UserRole.COMMUTER) -> User:
    return User(
        id=uuid.uuid4(), email="x@y.demo", password_hash="x",
        display_name="X", role=role, reputation=0.5,
    )


def test_sharing_is_off_unless_asked_for() -> None:
    """Consent is given, never assumed. A client that forgets the field has not
    consented on the user's behalf."""
    assert _attachment().is_public is False


def test_a_shared_recording_plays_for_anyone_including_signed_out() -> None:
    a = _attachment(is_public=True)
    assert may_play(a, _report(uuid.uuid4()), None) is True
    assert may_play(a, _report(uuid.uuid4()), _user()) is True


def test_an_unshared_recording_is_silent_to_other_commuters() -> None:
    a = _attachment(is_public=False)
    assert may_play(a, _report(uuid.uuid4()), _user(UserRole.COMMUTER)) is False


def test_an_unshared_recording_is_silent_to_signed_out_visitors() -> None:
    assert may_play(_attachment(), _report(uuid.uuid4()), None) is False


def test_you_can_always_play_back_your_own() -> None:
    me = _user()
    assert may_play(_attachment(), _report(me.id), me) is True


@pytest.mark.parametrize("role", [UserRole.OFFICER, UserRole.WARDEN, UserRole.ADMIN])
def test_the_control_room_can_play_anything(role: UserRole) -> None:
    """A warden being sent to a junction should hear why, shared or not."""
    assert may_play(_attachment(is_public=False), _report(uuid.uuid4()), _user(role)) is True


def test_consent_is_recorded_per_attachment_not_per_user() -> None:
    """One recording shared does not share the next one."""
    shared, private = _attachment(is_public=True), _attachment(is_public=False)
    stranger = _user()
    assert may_play(shared, _report(uuid.uuid4()), stranger) is True
    assert may_play(private, _report(uuid.uuid4()), stranger) is False


def test_visibility_is_expressed_in_the_api_response() -> None:
    """A reporter must be able to see whether their recording is currently shared,
    or the withdrawal option is meaningless."""
    from app.schemas import AttachmentResponse, VisibilityRequest

    assert "is_public" in AttachmentResponse.model_fields
    assert "is_public" in VisibilityRequest.model_fields


# =============================================================================
# THE EVIDENCE BONUS
# =============================================================================


def test_recorded_evidence_counts_for_more() -> None:
    """A recording is harder to fabricate from an armchair than a tapped coordinate."""
    plain = report_weight(0.5, 0.0)
    recorded = report_weight(0.5, 0.0, recorded_evidence=True)
    assert recorded > plain
    assert recorded == pytest.approx(plain * EVIDENCE_BONUS)


def test_the_bonus_cannot_lift_a_report_past_the_single_report_ceiling() -> None:
    """Otherwise attaching any audio file would buy credibility. Corroboration must
    remain the only route to verification."""
    strongest = report_weight(1.0, 0.0, recorded_evidence=True)
    assert strongest <= DEFAULT_EVIDENCE_STRENGTH
    assert strongest < THRESHOLD_VERIFIED


@given(
    reputation=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
    age=st.floats(0.0, 500.0, allow_nan=False, allow_infinity=False),
)
def test_evidence_never_lowers_a_weight_and_never_breaks_the_bound(
    reputation: float, age: float
) -> None:
    plain = report_weight(reputation, age)
    recorded = report_weight(reputation, age, recorded_evidence=True)
    assert recorded >= plain
    assert 0.0 <= recorded <= DEFAULT_EVIDENCE_STRENGTH


def test_a_recorded_report_from_a_discredited_account_is_still_weak() -> None:
    """Evidence multiplies reputation rather than replacing it. Someone with a poor
    record cannot restore their standing by attaching audio."""
    assert report_weight(0.05, 0.0, recorded_evidence=True) < 0.05


def test_the_bonus_is_modest() -> None:
    """Large enough to matter, small enough that it cannot be gamed into significance."""
    assert 1.0 < EVIDENCE_BONUS <= 1.5


def test_score_without_the_evidence_set_behaves_exactly_as_before() -> None:
    """The parameter is optional, so every existing caller and test is unaffected."""
    import datetime as dt
    import uuid

    from app.confidence import score

    now = dt.datetime(2026, 8, 13, 7, 0, tzinfo=dt.timezone.utc)
    reports = [(uuid.UUID(int=i + 1), 0.5, now) for i in range(3)]
    assert score(reports, now=now).confidence == score(
        reports, now=now, with_recorded_evidence=set()
    ).confidence


def test_score_applies_the_bonus_only_to_named_reports() -> None:
    import datetime as dt
    import uuid

    from app.confidence import score

    now = dt.datetime(2026, 8, 13, 7, 0, tzinfo=dt.timezone.utc)
    a, b = uuid.UUID(int=1), uuid.UUID(int=2)
    result = score([(a, 0.5, now), (b, 0.5, now)], now=now, with_recorded_evidence={a})

    weights = {e.report_id: e.weight for e in result.evidence}
    assert weights[a] > weights[b]


# =============================================================================
# SIGNED MEDIA URLS
#
# `<img src>` and `<audio src>` cannot send an Authorization header — the browser makes
# those requests on its own. So a private attachment was, in practice, unviewable by
# everybody, its own uploader included: listed in the interface, blank on the page, and a
# bare {"detail":"No such attachment."} if you pasted the URL into the address bar.
#
# The fix is a short-lived signed token in the URL, minted where the caller is known.
# These tests are about the ways that could go wrong.
# =============================================================================

SECRET = "a-test-secret-that-is-long-enough-to-be-plausible"
OTHER_SECRET = "a-completely-different-secret-of-similar-length"


def test_a_minted_token_opens_the_attachment_it_was_minted_for() -> None:
    aid = uuid.uuid4()
    assert media_tokens.permits(media_tokens.mint(aid, SECRET), aid, SECRET)


def test_a_token_does_not_open_a_different_attachment() -> None:
    """Otherwise one shared photograph would be a key to every private recording."""
    mine, yours = uuid.uuid4(), uuid.uuid4()
    assert not media_tokens.permits(media_tokens.mint(mine, SECRET), yours, SECRET)


def test_a_token_signed_with_another_secret_is_refused() -> None:
    aid = uuid.uuid4()
    assert not media_tokens.permits(media_tokens.mint(aid, OTHER_SECRET), aid, SECRET)


def test_an_expired_token_is_refused() -> None:
    aid = uuid.uuid4()
    stale = media_tokens.mint(aid, SECRET, ttl_seconds=-1)
    assert not media_tokens.permits(stale, aid, SECRET)


def test_the_token_expires_in_minutes_not_hours() -> None:
    """A URL copied out of a page should be worthless by the time anyone reads it."""
    assert 0 < media_tokens.TTL_SECONDS <= 900


@pytest.mark.parametrize("token", [None, "", "not-a-token", "a.b.c"])
def test_junk_is_refused_without_raising(token: str | None) -> None:
    """A malformed token is an answer of "no", not a 500. Anything else turns a bad URL
    into an error report from the server."""
    assert not media_tokens.permits(token, uuid.uuid4(), SECRET)


def test_a_login_token_cannot_be_used_as_a_media_token() -> None:
    """Both are signed with the same secret. Without an audience claim they would be
    interchangeable, and any session token would open any attachment."""
    aid = uuid.uuid4()
    login = create_access_token(str(aid), "commuter", SECRET)
    assert not media_tokens.permits(login, aid, SECRET)


def test_a_media_token_cannot_be_used_as_a_login_token() -> None:
    """And the reverse, which is the more serious direction: a media URL leaks easily —
    it appears in browser history and in a referrer — and must never become a session."""
    aid = uuid.uuid4()
    token = media_tokens.mint(aid, SECRET)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, SECRET)


def test_the_token_does_not_name_the_viewer() -> None:
    """It is a capability, not an identity: it grants sight of one file for ten minutes.
    Putting the viewer in it would make an image URL a record of who looked."""
    aid = uuid.uuid4()
    claims = jwt.decode(
        media_tokens.mint(aid, SECRET), SECRET,
        algorithms=["HS256"], audience="nkwanta:media",
    )
    assert set(claims) == {"sub", "aud", "iat", "exp"}


def test_a_served_url_carries_a_token_that_works() -> None:
    """The end-to-end shape, without a database: what the API hands the browser must be
    something the browser can actually load."""
    a = _attachment()
    url = attachment_url(a, SECRET)
    assert url.startswith(f"/attachments/{a.id}?t=")
    assert media_tokens.permits(url.split("?t=", 1)[1], a.id, SECRET)


# =============================================================================
# TWO DEFAULTS, DELIBERATELY DIFFERENT
# =============================================================================


def test_a_photograph_is_shared_by_default_and_a_recording_is_not() -> None:
    """D-042. They are not the same kind of evidence.

    A recording carries the reporter's voice, so sharing it exposes the person making the
    accusation — the thing NFR-4a exists to prevent. A photograph of a flooded road
    describes the road, and is the single most useful thing another commuter can be
    shown. Defaulting it to private meant nobody ever saw one.
    """
    signature = inspect.signature(upload_photo)
    assert signature.parameters["share_publicly"].default is True

    voice_signature = inspect.signature(upload_voice)
    assert voice_signature.parameters["share_publicly"].default is False


def test_an_image_renders_in_place_and_anything_else_downloads() -> None:
    """`inline` is safe on an image and only on an image: the type was checked against an
    allow-list on the way in, it is echoed back rather than guessed, and `nosniff` stops
    the browser overruling it. Audio keeps `attachment`, because its containers can hold
    almost anything."""
    source = inspect.getsource(fetch_attachment)
    assert "ALLOWED_IMAGE" in source
    assert "nosniff" in source
