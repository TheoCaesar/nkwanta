"""Application settings.

Everything configurable comes from environment variables so that the same code runs
unchanged locally and on Render. Nothing secret is ever committed.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

# Query parameters that libpq (and therefore Neon's copy-paste connection string)
# understands but the asyncpg driver rejects outright. Stripped in _normalise_db_url.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "options", "target_session_attrs"}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}


def _normalise_db_url(url: str) -> str:
    """Turn any Postgres URL into one asyncpg will accept.

    Neon hands you a string like::

        postgresql://user:pw@ep-x.eu-central-1.aws.neon.tech/nkwanta?sslmode=require

    Three things are wrong with that for our purposes:

    1. SQLAlchemy needs the driver named explicitly -> postgresql+asyncpg://
    2. asyncpg raises TypeError on 'sslmode' -- it spells the option 'ssl'
    3. Heroku-style URLs sometimes start 'postgres://', which SQLAlchemy dropped

    This function fixes all three. It is boring, and it is the single most common
    reason a first deploy to Neon fails.
    """
    if not url:
        return url

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]

    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in _LIBPQ_ONLY_PARAMS]

    # Neon requires TLS. Local development almost never has it.
    host = (parts.hostname or "").lower()
    if host and host not in _LOCAL_HOSTS and not any(k == "ssl" for k, _ in query):
        query.append(("ssl", "require"))

    return urlunsplit(parts._replace(query=urlencode(query)))


def to_sync_url(async_url: str) -> str:
    """asyncpg URL -> psycopg2 URL. Only needed by tooling that cannot do async."""
    return async_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Nkwanta"
    app_version: str = "0.1.0"
    environment: str = "development"

    # Empty by default so the application still boots with no database attached.
    # This matters: the first deploy goes out before Neon is wired up, and a service
    # that refuses to start cannot be debugged from its logs.
    database_url: str = ""

    # --- Clustering parameters -------------------------------------------------
    # The two most important numbers in the system. Provisional until tuned against
    # real data; the fact that they are guesses is recorded in the debt register.
    cluster_radius_metres: int = 300
    cluster_window_minutes: int = 30

    # --- Confidence decay ------------------------------------------------------
    # Half-life in minutes: how long before a report contributes half as much.
    confidence_half_life_minutes: int = 45

    @property
    def sqlalchemy_url(self) -> str:
        return _normalise_db_url(self.database_url)

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
