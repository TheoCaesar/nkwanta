"""The data model.

Five tables, and the split between them is the whole architecture:

    users             people, and how much their reports have been trusted
    reports           what people actually told us. WRITTEN ONCE, NEVER UPDATED.
    incidents         our current interpretation. CALCULATED from reports.
    incident_reports  which reports belong to which incident
    outbox            notifications still owed

The important line is between `reports` and `incidents`.

A report is a permanent note: "this person said this thing, here, at this time."
Nothing ever edits it. Even a report later shown to be false stays exactly as it is —
a contradiction is recorded as a *new* report, not as a change to the old one.

An incident is a projection: worked out by reading the reports and grouping them, the
way a bank balance is worked out by reading transactions rather than being stored as a
fact. Everything in `incidents` and `incident_reports` can be deleted and rebuilt from
`reports` alone, and that is exactly what the replay property test asserts.

Because of this, no code anywhere may UPDATE a row in `reports`. If you find yourself
wanting to, you want a new report instead.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Optional

from geoalchemy2 import Geography
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Longitude/latitude on the standard globe. 4326 is the coordinate system GPS uses,
# so phone coordinates go in without conversion.
WGS84 = 4326


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --- enumerations -------------------------------------------------------------
# Stored as VARCHAR with a CHECK constraint rather than a native PostgreSQL ENUM.
# Native enums need an ALTER TYPE to add a value, which is awkward in a migration and
# cannot run inside a transaction on older servers. Adding a seventh incident type
# should be a one-line constraint change, not a schema surgery.


class UserRole(str, enum.Enum):
    """Four roles, and only the first can be self-registered.

    Note what is *not* here: there is no separate "driver" role. A driver and a
    passenger have identical permissions — both report, both receive warnings. The
    difference between them is a client-side mode, not an account type: when the app
    detects motion it goes read-only and offers voice input instead of the keyboard
    (NFR-3). Making driving a role would have implied the server can tell who is
    driving, which it cannot and should not.
    """

    COMMUTER = "commuter"    # motorists, passengers, pedestrians — anyone on the road
    WARDEN = "warden"        # field traffic warden; receives assignments, confirms resolution
    OFFICER = "officer"      # MTTD control room; triages the queue, assigns wardens
    ADMIN = "admin"          # user management, moderation, threshold tuning


class IncidentType(str, enum.Enum):
    ACCIDENT = "accident"
    FLOOD = "flood"
    CLOSURE = "closure"
    SIGNAL_OUTAGE = "signal_outage"
    ROADWORKS = "roadworks"
    SURFACE_DEFECT = "surface_defect"


class IncidentStatus(str, enum.Enum):
    """The lifecycle. Transitions are guarded in B08 — not every move is legal."""

    REPORTED = "reported"          # one report, unconfirmed
    CORROBORATED = "corroborated"  # independent reports agree
    VERIFIED = "verified"          # confidence above the escalation threshold
    ASSIGNED = "assigned"          # an officer has sent someone
    RESOLVED = "resolved"


def _enum(py_enum: type[enum.Enum], name: str) -> Enum:
    return Enum(
        py_enum,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


# --- users --------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), nullable=False, default=UserRole.COMMUTER
    )

    # Reputation: how much this person's reports have been worth believing.
    # Starts at 0.5 — a new account is neither trusted nor distrusted. Moves with
    # outcomes. This is the defence against fabricated reports, because an unknown
    # account cannot on its own push an incident over the escalation threshold.
    reputation: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    reports_confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reports_contradicted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    reports: Mapped[list["Report"]] = relationship(back_populates="reporter")

    __table_args__ = (
        CheckConstraint("reputation >= 0.0 AND reputation <= 1.0", name="ck_users_reputation_range"),
        CheckConstraint("reports_confirmed >= 0", name="ck_users_confirmed_non_negative"),
        CheckConstraint("reports_contradicted >= 0", name="ck_users_contradicted_non_negative"),
        Index("ix_users_email", "email"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} {self.role.value} rep={self.reputation:.2f}>"


# --- reports — immutable ------------------------------------------------------


class Report(Base):
    """One thing one person told us. Append-only.

    NEVER UPDATE A ROW IN THIS TABLE. The audit trail, the replay property and the
    ability to re-cluster after fixing a bug all depend on it staying untouched.
    """

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    incident_type: Mapped[IncidentType] = mapped_column(
        _enum(IncidentType, "incident_type"), nullable=False
    )

    # Geography rather than Geometry: distances come back in metres on the curved
    # earth, so "within 300 m" means 300 m in Accra and 300 m anywhere else. With
    # Geometry the same query returns degrees, which vary with latitude.
    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=WGS84, spatial_index=False), nullable=False
    )

    # Two clocks, deliberately. occurred_at is when the reporter says it happened and
    # can be wrong or dishonest. received_at is our own server clock and cannot be.
    # Clustering uses occurred_at; auditing uses received_at.
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Client-supplied. A phone on a bad connection retries; the same key means the
    # same report, so a retry cannot inflate an incident's confidence by counting twice.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Set when this report contradicts an earlier one ("I drove past, it is clear").
    # Still an append: a new row pointing at the old, never an edit of the old.
    contradicts_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )

    reporter: Mapped["User"] = relationship(back_populates="reports")
    incidents: Mapped[list["IncidentReport"]] = relationship(back_populates="report")

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_reports_idempotency_key"),
        # Clustering asks: same type, near here, around then. This index serves the
        # first and last parts; the GiST index below serves the middle.
        Index("ix_reports_type_occurred", "incident_type", "occurred_at"),
        Index("ix_reports_received_at", "received_at"),
        Index("ix_reports_reporter", "reporter_id"),
        # Spatial index created explicitly in the migration — see 0002.
        Index("ix_reports_location", "location", postgresql_using="gist"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Report {self.incident_type.value} at {self.occurred_at:%Y-%m-%d %H:%M}>"


# --- incidents — a projection, rebuildable ------------------------------------


class Incident(Base):
    """Our current interpretation of a group of reports.

    Everything here is derived. Drop this table and `incident_reports`, replay every
    report through the clustering rules, and you must get back exactly what was there.
    That is asserted by the replay property test.
    """

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    incident_type: Mapped[IncidentType] = mapped_column(
        _enum(IncidentType, "incident_type"), nullable=False
    )

    # Mean position of the contributing reports.
    centroid: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=WGS84, spatial_index=False), nullable=False
    )

    first_reported_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_reported_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 0.0 = nobody believes this. 1.0 = certain. Built from the reputation of everyone
    # who reported it, decayed by how long ago they did. Recomputed, never accumulated,
    # so it does not depend on the order reports arrived in.
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[IncidentStatus] = mapped_column(
        _enum(IncidentStatus, "incident_status"), nullable=False, default=IncidentStatus.REPORTED
    )
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=_utcnow
    )

    reports: Mapped[list["IncidentReport"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_incidents_confidence_range"),
        CheckConstraint("report_count >= 0", name="ck_incidents_report_count_non_negative"),
        CheckConstraint("last_reported_at >= first_reported_at", name="ck_incidents_time_order"),
        Index("ix_incidents_type_status", "incident_type", "status"),
        Index("ix_incidents_last_reported", "last_reported_at"),
        Index("ix_incidents_centroid", "centroid", postgresql_using="gist"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Incident {self.incident_type.value} {self.status.value} "
            f"conf={self.confidence:.2f} n={self.report_count}>"
        )


class IncidentReport(Base):
    """Which reports make up which incident. Part of the projection, so rebuildable."""

    __tablename__ = "incident_reports"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True
    )
    # This report's contribution to the incident's confidence at the time of the last
    # recompute. Stored so the score can be explained to an officer, not just asserted.
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    incident: Mapped["Incident"] = relationship(back_populates="reports")
    report: Mapped["Report"] = relationship(back_populates="incidents")

    __table_args__ = (
        # One report belongs to at most one incident. If clustering ever tries to put a
        # report in two, the database refuses — the bug surfaces here rather than as a
        # quietly double-counted confidence score.
        UniqueConstraint("report_id", name="uq_incident_reports_report"),
        Index("ix_incident_reports_incident", "incident_id"),
    )


# --- outbox — notifications still owed ----------------------------------------


class OutboxMessage(Base):
    """A note-to-self: "this still needs sending."

    Written in the SAME database transaction as the report that caused it. That is the
    entire point. Save the report and the note together, or save neither — so a crash
    between the two is impossible, and no report can be accepted that nobody is ever
    warned about.

    A separate worker drains this table. See docs/04-advanced-concept.md section 5.
    """

    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)

    aggregate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Unique. Delivery is at-least-once — if the gateway does not answer we cannot tell
    # whether the message went out, so we resend. This key is what stops the recipient
    # being warned twice. Send it five times, the user hears once.
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_outbox_idempotency_key"),
        CheckConstraint("attempts >= 0", name="ck_outbox_attempts_non_negative"),
        # Partial index: the worker only ever asks for unprocessed rows, and this keeps
        # that query fast no matter how many processed rows accumulate behind it.
        Index(
            "ix_outbox_unprocessed",
            "created_at",
            postgresql_where=(processed_at.is_(None)),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        state = "pending" if self.processed_at is None else "sent"
        return f"<Outbox {self.event_type} {state} attempts={self.attempts}>"
