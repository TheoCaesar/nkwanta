"""B01 acceptance tests — the skeleton stands up.

These run without a database. That is the point: the first deploy goes out before
Neon is wired in, and a service that cannot start without its database cannot be
diagnosed from its own logs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import _normalise_db_url, to_sync_url
from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# --- liveness ----------------------------------------------------------------

def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "Nkwanta"
    assert "uptime_seconds" in body


def test_health_does_not_require_a_database(client: TestClient) -> None:
    """Liveness must never touch the database — the keep-warm ping hits it every
    ten minutes and free-tier compute is metered."""
    assert client.get("/health").status_code == 200


def test_ready_reports_degraded_without_a_database(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] in {"ok", "degraded", "error"}


# --- the static page ---------------------------------------------------------

def test_index_page_is_served(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Nkwanta" in r.text


def test_openapi_docs_available(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200


# --- connection string normalisation -----------------------------------------
# This is where a first deploy to Neon usually dies, so it is tested directly.

@pytest.mark.parametrize(
    "raw,expected_driver",
    [
        ("postgresql://u:p@host/db", "postgresql+asyncpg://"),
        ("postgres://u:p@host/db", "postgresql+asyncpg://"),
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://"),
    ],
)
def test_driver_is_normalised(raw: str, expected_driver: str) -> None:
    assert _normalise_db_url(raw).startswith(expected_driver)


def test_sslmode_is_stripped_and_ssl_added() -> None:
    """asyncpg raises TypeError on 'sslmode'. Neon hands you exactly that."""
    out = _normalise_db_url(
        "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/nkwanta?sslmode=require"
    )
    assert "sslmode" not in out
    assert "ssl=require" in out


def test_localhost_does_not_get_ssl() -> None:
    out = _normalise_db_url("postgresql://u:p@localhost:5432/nkwanta")
    assert "ssl=" not in out


def test_channel_binding_is_stripped() -> None:
    out = _normalise_db_url(
        "postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require"
    )
    assert "channel_binding" not in out


def test_empty_url_survives() -> None:
    assert _normalise_db_url("") == ""


def test_sync_url_round_trip() -> None:
    async_url = _normalise_db_url("postgresql://u:p@localhost/db")
    assert to_sync_url(async_url).startswith("postgresql://")
