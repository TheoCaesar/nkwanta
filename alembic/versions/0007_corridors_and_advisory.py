"""Corridors, subscriptions, notifications, and a stable incident identity.

Revision ID: 0007
Revises: 0006
Created: 2026-08-13

A corridor is a LINESTRING, not a point with a radius. "Is this incident on my route?"
is a question about distance from a line, which PostGIS answers directly. A circle
covering the 20 km Tema Motorway would cover half of Accra.

`incidents.cluster_key` is the other half of this change and matters more than it looks.
Incident rows are deleted and recreated on every rebuild, so their primary keys cannot
be used to remember anything about them — a notification keyed on `incidents.id` would
be orphaned by the next report to arrive nearby. The cluster key is the smallest
contributing report id, which is stable because cluster membership is order-independent.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WGS84 = 4326
INCIDENT_TYPES = ("accident", "flood", "closure", "signal_outage", "roadworks", "surface_defect")


def upgrade() -> None:
    # --- corridors ------------------------------------------------------------
    op.create_table(
        "corridors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column(
            "path",
            Geography(geometry_type="LINESTRING", srid=WGS84, spatial_index=False),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_corridors_name"),
    )
    op.create_index("ix_corridors_path", "corridors", ["path"], postgresql_using="gist")

    # --- subscriptions --------------------------------------------------------
    op.create_table(
        "corridor_subscriptions",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("corridor_id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["corridor_id"], ["corridors.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_corridor_subscriptions_corridor", "corridor_subscriptions", ["corridor_id"]
    )

    # --- notifications --------------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("incident_key", sa.Uuid(), nullable=False),
        sa.Column("corridor_id", sa.Uuid(), nullable=True),
        sa.Column("incident_type", sa.String(32), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["corridor_id"], ["corridors.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "incident_type IN (" + ", ".join(f"'{t}'" for t in INCIDENT_TYPES) + ")",
            name="ck_notifications_incident_type",
        ),
        # The constraint that makes at-least-once delivery survivable. The worker may
        # process the same advisory repeatedly; the recipient is warned once.
        sa.UniqueConstraint("user_id", "incident_key", name="uq_notifications_once_per_incident"),
    )
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at"]
    )

    # --- stable incident identity ---------------------------------------------
    # Added with a generated default so existing rows remain valid. Every rebuild
    # overwrites it with the real cluster key, and incidents are fully derived data, so
    # the placeholder is short-lived by construction.
    op.add_column(
        "incidents",
        sa.Column("cluster_key", sa.Uuid(), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
    )
    op.create_index("ix_incidents_cluster_key", "incidents", ["cluster_key"])


def downgrade() -> None:
    op.drop_index("ix_incidents_cluster_key", table_name="incidents")
    op.drop_column("incidents", "cluster_key")
    op.drop_table("notifications")
    op.drop_table("corridor_subscriptions")
    op.drop_table("corridors")
