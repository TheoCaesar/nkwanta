"""Record how an incident ended.

Revision ID: 0004
Revises: 0003
Created: 2026-08-13

`resolved_at` already said *when* an incident closed. This says *whether it was real*.

That distinction drives reporter reputation: a confirmed incident vindicates everyone
who reported it, a false alarm contradicts them. Without both outcomes, reputation could
only ever rise and a fabricated report would cost its author nothing.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RESOLUTIONS = ("confirmed", "false_alarm")


def upgrade() -> None:
    op.add_column("incidents", sa.Column("resolution", sa.String(20), nullable=True))
    op.add_column("incidents", sa.Column("resolution_note", sa.Text(), nullable=True))

    joined = ", ".join(f"'{r}'" for r in RESOLUTIONS)
    # NULL while unresolved, one of the two values afterwards. The second clause makes
    # "resolved with no stated outcome" unrepresentable rather than merely discouraged.
    op.create_check_constraint(
        "ck_incidents_resolution",
        "incidents",
        f"resolution IS NULL OR resolution IN ({joined})",
    )
    op.create_check_constraint(
        "ck_incidents_resolution_requires_time",
        "incidents",
        "(resolution IS NULL) = (resolved_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_incidents_resolution_requires_time", "incidents", type_="check")
    op.drop_constraint("ck_incidents_resolution", "incidents", type_="check")
    op.drop_column("incidents", "resolution_note")
    op.drop_column("incidents", "resolution")
