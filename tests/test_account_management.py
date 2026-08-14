"""Account management — editing yourself, changing your password, admin controls.

Three endpoints added for the rebuilt interface. The tests that matter here are the ones
about what a request is *not allowed to contain*, because that is where privilege
escalation would live.
"""

from __future__ import annotations

import pytest
import pydantic

from app.schemas import ChangePasswordRequest, UpdateMeRequest, UpdateUserByAdmin
from app.security import hash_password, verify_password


# =============================================================================
# WHAT YOU MAY CHANGE ABOUT YOURSELF
# =============================================================================


def test_you_can_only_change_your_display_name() -> None:
    """The whole schema is one field. Anything else an attacker wants to change has no
    input to arrive through."""
    assert set(UpdateMeRequest.model_fields) == {"display_name"}


def test_you_cannot_change_your_own_role() -> None:
    """Same reasoning as registration: not a check that could be forgotten, an input
    that does not exist. Nobody promotes themselves."""
    body = UpdateMeRequest.model_validate({"display_name": "Ama Owusu", "role": "admin"})
    assert not hasattr(body, "role")


def test_you_cannot_change_your_own_email() -> None:
    """Email is the login identifier. Changing it needs a verification message this
    system cannot send, so it is fixed rather than quietly editable."""
    body = UpdateMeRequest.model_validate(
        {"display_name": "Ama Owusu", "email": "someone@else.com"}
    )
    assert not hasattr(body, "email")


def test_you_cannot_change_your_own_reputation() -> None:
    """Reputation gates whether reports reach the police. Self-editable trust would make
    the whole confidence model meaningless."""
    body = UpdateMeRequest.model_validate({"display_name": "Ama", "reputation": 0.99})
    assert not hasattr(body, "reputation")


@pytest.mark.parametrize("name", ["", "A"])
def test_a_display_name_must_be_usable(name: str) -> None:
    with pytest.raises(pydantic.ValidationError):
        UpdateMeRequest(display_name=name)


def test_a_display_name_has_an_upper_bound() -> None:
    with pytest.raises(pydantic.ValidationError):
        UpdateMeRequest(display_name="x" * 81)


# =============================================================================
# CHANGING A PASSWORD
# =============================================================================


def test_the_current_password_is_required() -> None:
    """A valid token proves possession of a device, not knowledge of a secret. Without
    this, anyone holding an unlocked phone could lock its owner out."""
    assert "current_password" in ChangePasswordRequest.model_fields
    with pytest.raises(pydantic.ValidationError):
        ChangePasswordRequest(new_password="longenough1")


def test_the_new_password_obeys_the_same_rules_as_registration() -> None:
    with pytest.raises(pydantic.ValidationError):
        ChangePasswordRequest(current_password="old", new_password="short")
    with pytest.raises(pydantic.ValidationError):
        ChangePasswordRequest(current_password="old", new_password="x" * 73)


def test_a_changed_password_actually_replaces_the_old_hash() -> None:
    """The behaviour the endpoint depends on, verified at the level it is implemented."""
    original = hash_password("first-password")
    assert verify_password("first-password", original)

    replacement = hash_password("second-password")
    assert verify_password("second-password", replacement)
    assert not verify_password("first-password", replacement)


def test_two_hashes_of_one_password_differ() -> None:
    """Salted, so changing to the same password still produces a different hash and
    cannot be detected by comparing stored values."""
    assert hash_password("same") != hash_password("same")


# =============================================================================
# ADMIN CHANGES TO SOMEBODY ELSE
# =============================================================================


def test_an_admin_may_change_role_and_activity_only() -> None:
    assert set(UpdateUserByAdmin.model_fields) == {"is_active", "role"}


def test_omitted_fields_mean_unchanged_not_null() -> None:
    """A partial update must not blank out what it does not mention."""
    body = UpdateUserByAdmin(is_active=False)
    assert body.role is None
    assert body.is_active is False


def test_an_admin_cannot_edit_anyones_password_directly() -> None:
    """Resetting somebody's password without their knowledge is a different and much
    larger power than deactivating them. It is deliberately absent."""
    assert "password" not in UpdateUserByAdmin.model_fields
    assert "password_hash" not in UpdateUserByAdmin.model_fields


def test_an_admin_cannot_edit_reputation() -> None:
    """Reputation is earned through confirmed reports. Hand-editing it would let an
    administrator manufacture a trusted account."""
    assert "reputation" not in UpdateUserByAdmin.model_fields


# =============================================================================
# THE ROUTES EXIST AND ARE DOCUMENTED
# =============================================================================


@pytest.mark.parametrize(
    "method,path",
    [("patch", "/auth/me"), ("post", "/auth/me/password"), ("patch", "/auth/users/{x}")],
)
def test_the_route_is_registered(method: str, path: str) -> None:
    import re

    from app.main import app

    documented = {
        re.sub(r"\{[^}]+\}", "{x}", p): set(ops)
        for p, ops in app.openapi()["paths"].items()
    }
    assert path in documented, f"{path} is not in the API schema"
    assert method in documented[path]
