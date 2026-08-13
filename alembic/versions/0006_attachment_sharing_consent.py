"""Let a reporter choose whether their recording is shared publicly.

Revision ID: 0006
Revises: 0005
Created: 2026-08-13

Attachments were originally readable only by the person who uploaded them and the
control room, on the grounds that a voice recording identifies its speaker.

That reasoning was half right and cost more than it needed to. It conflated two
different concerns — protecting a *reported party* from harassment, which is what NFR-4
actually says, and protecting a *reporter* from being identified, which is a separate and
weaker argument for most incident types. A flood on Spintex Road accuses nobody.

It also threw away most of the value of capturing voice. "Tipper truck across two lanes,
backed up to Odorna" tells a commuter far more than *accident, confidence 0.88*.

The reporter is the only person who knows whether their voice being public is a problem
for them. So they decide, and they can change their mind afterwards. Default is not
shared: consent must be given, never assumed.

See decision D-029, which supersedes D-028.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            # Existing rows were uploaded with no opportunity to consent, so they stay
            # private. Retroactively publishing them would be exactly the thing this
            # column exists to prevent.
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_attachments_public",
        "attachments",
        ["report_id"],
        postgresql_where=sa.text("is_public"),
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_public", table_name="attachments")
    op.drop_column("attachments", "is_public")
