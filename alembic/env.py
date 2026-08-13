"""Alembic environment, wired for async SQLAlchemy.

The connection string comes from DATABASE_URL via app.config, which normalises it
for asyncpg. Nothing secret lives in alembic.ini.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db import Base

# Importing the models module registers every table on Base.metadata so that
# autogenerate can see them. It is imported for that side effect alone.
try:  # pragma: no cover - models arrive in B02
    import app.models  # noqa: F401
except ImportError:  # pragma: no cover
    pass

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
if not settings.database_configured:
    raise SystemExit(
        "DATABASE_URL is not set.\n"
        "Copy .env.example to .env and paste your Neon connection string into it."
    )

config.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # PostGIS creates internal tables we must never try to manage.
        include_object=lambda obj, name, type_, reflected, compare_to: not (
            type_ == "table" and name in {"spatial_ref_sys", "geography_columns", "geometry_columns"}
        ),
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
