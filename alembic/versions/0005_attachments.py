"""Voice notes and photos attached to reports.

Revision ID: 0005
Revises: 0004
Created: 2026-08-13

A separate table rather than columns on `reports`, because `reports` is scanned
constantly by clustering and binary data in those rows would compete with that workload
for the buffer cache. Audio nobody is listening to should cost nothing.

The size cap is enforced here as well as in the upload handler. A limit that lives only
in application code is one a future endpoint can forget.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KINDS = ("voice", "photo")
MAX_BYTES = 524_288          # 512 KB


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("content_type", sa.String(60), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        # CASCADE: an attachment has no meaning without its report. Unlike reports
        # themselves, which survive user deletion under RESTRICT because they are the
        # evidence that justified sending a warden somewhere.
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in KINDS) + ")",
            name="ck_attachments_kind",
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_attachments_size_positive"),
        sa.CheckConstraint(f"byte_size <= {MAX_BYTES}", name="ck_attachments_size_limit"),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds > 0",
            name="ck_attachments_duration_positive",
        ),
    )
    op.create_index("ix_attachments_report", "attachments", ["report_id"])


def downgrade() -> None:
    op.drop_table("attachments")
