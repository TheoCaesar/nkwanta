"""B03 — authentication and authorisation.

Split into two groups, because they fail for different reasons and mean different
things:

    authentication  -- who is this?      (token handling, login, registration)
    authorisation   -- may they do this? (role guards)

The privilege-escalation tests are the ones that matter most. A commuter who can
assign a warden, or who can register themselves as police, is not a bug — it is the
whole system failing.

These use a stubbed database session so they run without PostgreSQL.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from typing_extensions import Annotated

from app.auth import get_current_user, require_role
from app.config import get_settings
from app.models import User, UserRole
from app.schemas import RegisterRequest
from app.security import create_access_token, hash_password

SECRET = "test-secret-at-least-thirty-two-bytes-long-abcdef"


def _user(role: UserRole = UserRole.COMMUTER, active: bool = True) -> User:
    u = User(
        id=uuid.uuid4(),
        email="ama@example.com",
        password_hash=hash_password("correct-horse"),
        display_name="Ama O.",
        role=role,
        reputation=0.5,
        reports_confirmed=0,
        reports_contradicted=0,
        is_active=active,
    )
    return u


def _app_with_user(user: User | None) -> FastAPI:
    """A tiny app whose only job is to exercise the guards."""
    app = FastAPI()

    async def _fake_current_user() -> User:
        if user is None:
            raise HTTPException(401, "Not authenticated")
        return user

    @app.get("/officer")
    async def officer_route(
        _u: Annotated[User, Depends(require_role(UserRole.OFFICER))]
    ) -> dict:
        return {"ok": True}

    @app.get("/control-room")
    async def control_room(
        _u: Annotated[User, Depends(require_role(UserRole.OFFICER, UserRole.ADMIN))]
    ) -> dict:
        return {"ok": True}

    @app.get("/warden")
    async def warden_route(
        _u: Annotated[User, Depends(require_role(UserRole.WARDEN))]
    ) -> dict:
        return {"ok": True}

    app.dependency_overrides[get_current_user] = _fake_current_user
    return app


# --- roles --------------------------------------------------------------------


def test_four_roles_exist() -> None:
    assert {r.value for r in UserRole} == {"commuter", "warden", "officer", "admin"}


def test_there_is_no_driver_role() -> None:
    """A driver and a passenger have identical permissions. Driving is a client-side
    mode (NFR-3), not an account type — the server cannot tell who is driving."""
    assert "driver" not in {r.value for r in UserRole}


# --- authorisation: the escalation tests --------------------------------------


def test_commuter_cannot_reach_an_officer_route() -> None:
    client = TestClient(_app_with_user(_user(UserRole.COMMUTER)))
    r = client.get("/officer")
    assert r.status_code == 403
    assert "officer" in r.json()["detail"]


def test_warden_cannot_reach_an_officer_route() -> None:
    """A warden goes where they are sent. Deciding who goes is the officer's job."""
    client = TestClient(_app_with_user(_user(UserRole.WARDEN)))
    assert client.get("/officer").status_code == 403


def test_officer_cannot_reach_a_warden_route() -> None:
    client = TestClient(_app_with_user(_user(UserRole.OFFICER)))
    assert client.get("/warden").status_code == 403


def test_admin_is_not_implicitly_allowed_everywhere() -> None:
    """Admins get what they are explicitly granted, nothing more. Implicit superuser
    access is how a permission system quietly stops meaning anything."""
    client = TestClient(_app_with_user(_user(UserRole.ADMIN)))
    assert client.get("/officer").status_code == 403      # not granted
    assert client.get("/control-room").status_code == 200  # granted


def test_officer_reaches_officer_routes() -> None:
    client = TestClient(_app_with_user(_user(UserRole.OFFICER)))
    assert client.get("/officer").status_code == 200


def test_unauthenticated_is_401_not_403() -> None:
    """401 means 'I do not know who you are'; 403 means 'I know, and no'. Returning
    403 to an anonymous caller tells them nothing about how to fix it."""
    client = TestClient(_app_with_user(None))
    assert client.get("/officer").status_code == 401


# --- registration cannot escalate ---------------------------------------------


def test_register_request_has_no_role_field() -> None:
    """Not a check that could be bypassed — an input that does not exist. There is no
    request body an attacker can craft that registers them as police."""
    assert "role" not in RegisterRequest.model_fields


def test_register_request_rejects_extra_role_key() -> None:
    body = RegisterRequest.model_validate(
        {"email": "x@y.com", "password": "longenough1", "display_name": "Ama", "role": "admin"}
    )
    assert not hasattr(body, "role")


@pytest.mark.parametrize("password", ["short", "1234567"])
def test_short_passwords_rejected(password: str) -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        RegisterRequest(email="a@b.com", password=password, display_name="Ama")


def test_password_over_bcrypt_limit_rejected_at_the_schema() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        RegisterRequest(email="a@b.com", password="a" * 73, display_name="Ama")


# --- tokens -------------------------------------------------------------------


def test_token_carries_subject_and_role() -> None:
    from app.security import decode_access_token

    token = create_access_token("abc-123", "officer", SECRET)
    claims = decode_access_token(token, SECRET)
    assert claims["sub"] == "abc-123"
    assert claims["role"] == "officer"
    assert "exp" in claims


def test_password_hash_is_absent_from_every_response_schema() -> None:
    """The single most important thing never to serialise."""
    from app.schemas import TokenResponse, UserResponse

    for schema in (UserResponse, TokenResponse):
        assert "password_hash" not in schema.model_fields
        assert "password" not in schema.model_fields


# --- configuration ------------------------------------------------------------


def test_default_jwt_secret_is_detectable() -> None:
    """main.py refuses to start in production while this is true."""
    settings = get_settings()
    assert settings.jwt_secret_is_default is True
    assert settings.jwt_expiry_minutes == 720
