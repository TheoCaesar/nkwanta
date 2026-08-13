"""Request and response shapes.

These are separate from the database models on purpose. A model describes what is
stored; a schema describes what crosses the wire. Keeping them apart means adding an
internal column cannot accidentally start leaking it to every client — the two only
move together when someone decides they should.

The clearest case is `password_hash`. It is on the model. It appears in no schema
anywhere, so there is no route by which it can be serialised into a response.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.lifecycle import Resolution
from app.models import AttachmentKind, IncidentStatus, IncidentType, UserRole


# --- authentication -----------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(min_length=2, max_length=80)

    # Note the absence of a `role` field. Self-registration always produces a
    # commuter. Accepting a role here would let anyone register as police.


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: UserRole
    reputation: float
    reports_confirmed: int
    reports_contradicted: int
    created_at: dt.datetime


class UserCreateByAdmin(BaseModel):
    """Only an admin may call this, and it is the only way to mint a privileged
    account. Wardens, officers and other admins are created here or seeded."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(min_length=2, max_length=80)
    role: UserRole


class ErrorResponse(BaseModel):
    detail: str


# --- reports ------------------------------------------------------------------


class ReportCreate(BaseModel):
    incident_type: IncidentType
    latitude: float = Field(ge=-90, le=90, description="Degrees north. Accra is about 5.6")
    longitude: float = Field(ge=-180, le=180, description="Degrees east. Accra is about -0.2")
    occurred_at: dt.datetime | None = Field(
        default=None,
        description="When it happened. Defaults to now. Must not be in the future.",
    )
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Optional. Supply a unique value per report and a retry on a bad "
            "connection cannot create a duplicate."
        ),
    )


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_type: IncidentType
    latitude: float
    longitude: float
    occurred_at: dt.datetime
    received_at: dt.datetime
    note: str | None
    reporter_id: uuid.UUID


class EvidenceResponse(BaseModel):
    """One report's contribution to an incident's confidence.

    This is what makes the score explainable rather than merely displayed. An officer
    can see which reporter, how reliable they have been, and how much that particular
    report counted.
    """

    report_id: uuid.UUID
    reporter_name: str
    reporter_reputation: float
    occurred_at: dt.datetime
    weight: float


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_type: IncidentType
    latitude: float
    longitude: float
    confidence: float
    status: IncidentStatus
    report_count: int
    first_reported_at: dt.datetime
    last_reported_at: dt.datetime
    assigned_to_id: uuid.UUID | None = None
    resolved_at: dt.datetime | None = None


class IncidentDetailResponse(IncidentResponse):
    evidence: list[EvidenceResponse]
    allowed_actions: list[str] = []


# --- dispatch -----------------------------------------------------------------


class AssignRequest(BaseModel):
    warden_id: uuid.UUID


class ResolveRequest(BaseModel):
    resolution: Resolution
    note: str | None = Field(default=None, max_length=500)


class ReputationChange(BaseModel):
    user_id: uuid.UUID
    display_name: str
    reputation: float
    reports_confirmed: int
    reports_contradicted: int


class ResolveResponse(BaseModel):
    incident: IncidentResponse
    reputations_updated: list[ReputationChange]


class AttachmentResponse(BaseModel):
    """Metadata only. The bytes are fetched separately from `url`, and that route is
    restricted — a voice note identifies its speaker."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_id: uuid.UUID
    kind: AttachmentKind
    content_type: str
    byte_size: int
    duration_seconds: float | None
    created_at: dt.datetime
    url: str
    is_public: bool


class VisibilityRequest(BaseModel):
    """Consent is withdrawable. A choice that cannot be reversed is not a choice."""

    is_public: bool


class WardenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    reputation: float


class ReportAccepted(BaseModel):
    """Returned by POST /reports.

    `duplicate` tells the client whether this call created something. A retry that
    lands on an existing idempotency key gets the original report back and
    `duplicate: true`, rather than an error — the caller's intent was satisfied, and
    a 409 would push them towards retrying again.
    """

    report: ReportResponse
    duplicate: bool
