"""B02 — the data model holds the shape the architecture depends on.

These tests need no database. They interrogate the SQLAlchemy metadata directly, which
means they run in milliseconds and catch the mistakes that actually happen: an index
quietly dropped during a refactor, a uniqueness constraint that was meant to be there.

The constraints checked here are not decoration. Each one turns a class of bug into an
error the database refuses rather than a wrong number nobody notices.
"""

from __future__ import annotations

import pytest

from app.models import (
    Incident,
    IncidentReport,
    IncidentStatus,
    IncidentType,
    OutboxMessage,
    Report,
    User,
    UserRole,
)


def _index_names(model) -> set[str]:
    return {ix.name for ix in model.__table__.indexes}


def _constraint_names(model) -> set[str]:
    return {c.name for c in model.__table__.constraints if c.name}


# --- the report/incident split -----------------------------------------------


def test_five_tables_exist() -> None:
    from app.db import Base

    assert {"users", "reports", "incidents", "incident_reports", "outbox"} <= set(
        Base.metadata.tables
    )


def test_reports_carry_two_independent_clocks() -> None:
    """occurred_at is what the reporter claims and may be wrong. received_at is our
    own server clock and cannot be. Clustering uses one, auditing the other."""
    cols = Report.__table__.columns
    assert "occurred_at" in cols
    assert "received_at" in cols
    assert not cols["occurred_at"].nullable
    assert not cols["received_at"].nullable


def test_reports_have_no_mutable_status_column() -> None:
    """Reports are append-only. A status field would invite an UPDATE, and the replay
    property depends on this table never being edited. A contradiction is a new row
    pointing at the old one via contradicts_id."""
    assert "status" not in Report.__table__.columns
    assert "contradicts_id" in Report.__table__.columns


def test_incident_fields_are_all_derivable_from_reports() -> None:
    """Everything on an incident must be recomputable, or replay cannot work."""
    derived = {
        "incident_type", "centroid", "first_reported_at",
        "last_reported_at", "confidence", "report_count",
    }
    assert derived <= set(Incident.__table__.columns.keys())


# --- constraints that turn bugs into errors ----------------------------------


def test_a_report_can_belong_to_only_one_incident() -> None:
    """If clustering ever places one report in two incidents, the database refuses.
    Without this the failure is silent — confidence quietly double-counted."""
    assert "uq_incident_reports_report" in _constraint_names(IncidentReport)


def test_report_idempotency_key_is_unique() -> None:
    """A phone on a bad connection retries. The same key must not create a second
    report, or a retry inflates the incident's confidence."""
    assert "uq_reports_idempotency_key" in _constraint_names(Report)


def test_outbox_idempotency_key_is_unique() -> None:
    """Delivery is at-least-once. This is what stops a resend warning someone twice."""
    assert "uq_outbox_idempotency_key" in _constraint_names(OutboxMessage)


def test_confidence_is_bounded() -> None:
    assert "ck_incidents_confidence_range" in _constraint_names(Incident)


def test_reputation_is_bounded() -> None:
    assert "ck_users_reputation_range" in _constraint_names(User)


def test_incident_times_cannot_be_inverted() -> None:
    assert "ck_incidents_time_order" in _constraint_names(Incident)


def test_counters_cannot_go_negative() -> None:
    assert "ck_incidents_report_count_non_negative" in _constraint_names(Incident)
    assert "ck_outbox_attempts_non_negative" in _constraint_names(OutboxMessage)


# --- indexes the clustering query depends on ---------------------------------


def test_reports_have_a_spatial_index() -> None:
    """'Everything within 300 metres of here' is unanswerable at speed without GiST.
    A btree orders one dimension only."""
    ix = next(i for i in Report.__table__.indexes if i.name == "ix_reports_location")
    assert ix.dialect_options["postgresql"]["using"] == "gist"


def test_incidents_have_a_spatial_index() -> None:
    ix = next(i for i in Incident.__table__.indexes if i.name == "ix_incidents_centroid")
    assert ix.dialect_options["postgresql"]["using"] == "gist"


def test_reports_indexed_by_type_and_time_together() -> None:
    """Clustering asks 'same type, around then' in one go, so the index is composite."""
    ix = next(i for i in Report.__table__.indexes if i.name == "ix_reports_type_occurred")
    assert [c.name for c in ix.columns] == ["incident_type", "occurred_at"]


def test_outbox_unprocessed_index_is_partial() -> None:
    """The worker only asks for unprocessed rows. A partial index stays small no
    matter how many processed rows accumulate."""
    ix = next(i for i in OutboxMessage.__table__.indexes if i.name == "ix_outbox_unprocessed")
    assert ix.dialect_options["postgresql"].get("where") is not None


# --- geography, not geometry --------------------------------------------------


@pytest.mark.parametrize("model,column", [(Report, "location"), (Incident, "centroid")])
def test_locations_use_geography_in_wgs84(model, column) -> None:
    """Geography returns distances in metres on a curved earth, so '300 m' means the
    same everywhere. Geometry would return degrees, which vary with latitude."""
    col = model.__table__.columns[column]
    assert col.type.srid == 4326
    assert col.type.geometry_type == "POINT"


# --- enumerations -------------------------------------------------------------


def test_six_incident_types() -> None:
    assert {t.value for t in IncidentType} == {
        "accident", "flood", "closure", "signal_outage", "roadworks", "surface_defect",
    }


def test_four_roles() -> None:
    """Warden added at 0003. A field warden is a distinct actor from a control-room
    officer: the officer decides who goes, the warden goes and confirms."""
    assert {r.value for r in UserRole} == {"commuter", "warden", "officer", "admin"}


def test_lifecycle_has_five_states() -> None:
    assert [s.value for s in IncidentStatus] == [
        "reported", "corroborated", "verified", "assigned", "resolved",
    ]


def test_enums_are_not_native_postgres_types() -> None:
    """VARCHAR + CHECK rather than a native ENUM. Adding a seventh incident type is
    then a constraint change, not an ALTER TYPE that cannot run in a transaction."""
    assert Report.__table__.columns["incident_type"].type.native_enum is False


# --- deletion behaviour -------------------------------------------------------


def test_reports_survive_user_deletion() -> None:
    """RESTRICT, not CASCADE. Deleting a user must never silently rewrite history by
    removing the reports that justified sending a warden somewhere."""
    fk = next(iter(Report.__table__.columns["reporter_id"].foreign_keys))
    assert fk.ondelete == "RESTRICT"


def test_projection_rows_cascade() -> None:
    """The projection is rebuildable, so cascading deletes are safe here — unlike on
    reports, where they would destroy the source of truth."""
    fk = next(iter(IncidentReport.__table__.columns["incident_id"].foreign_keys))
    assert fk.ondelete == "CASCADE"
