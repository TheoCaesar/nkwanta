"""Add the warden role.

Revision ID: 0003
Revises: 0002
Created: 2026-08-13

A field traffic warden is a distinct actor from a control-room officer: the officer
triages the queue and decides who goes; the warden goes, and confirms when the road is
clear. Tier 1 needs both ends of that loop.

This is the payoff for storing roles as VARCHAR + CHECK rather than a native PostgreSQL
enum. Adding a value is a constraint swap that runs inside an ordinary transaction. With
a native enum it would have been ALTER TYPE ... ADD VALUE, which historically could not
run in a transaction block at all.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ROLES = ("commuter", "officer", "admin")
NEW_ROLES = ("commuter", "warden", "officer", "admin")


def _check(values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"role IN ({joined})"


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", _check(NEW_ROLES))


def downgrade() -> None:
    # Any warden would violate the narrower constraint, so demote them first.
    op.execute("UPDATE users SET role = 'commuter' WHERE role = 'warden'")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", _check(OLD_ROLES))
