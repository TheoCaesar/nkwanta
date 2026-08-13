"""Enable the PostGIS extension.

Revision ID: 0001
Revises:
Created: 2026-08-12

PostGIS teaches PostgreSQL about maps -- points, distances, and "everything within
300 metres of here". The spatio-temporal clustering in B05 depends on it entirely.

Enabling it as a migration rather than by hand means the database can be rebuilt from
nothing by a single command, which is what makes the deployment reproducible.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # Deliberately not dropped. Other objects may depend on it, and dropping an
    # extension that another migration relies on fails in a confusing way.
    pass
