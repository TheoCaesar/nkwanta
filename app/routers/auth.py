"""Registration, login, and who-am-I.

The security decision worth defending here: **self-registration always produces a
commuter.** `RegisterRequest` has no role field at all, so there is no request an
attacker can craft to become an officer — it is not a check that could be bypassed,
it is an input that does not exist.

Privileged accounts come from exactly two places: the seed script, and an admin
calling POST /auth/users. Both are auditable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AdminOnly, CurrentUser
from app.config import Settings, get_settings
from app.db import get_session
from app.models import User, UserRole
from app.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserCreateByAdmin,
    UserResponse,
)
from app.security import PasswordTooLongError, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])

# Deliberately identical for "no such account" and "wrong password". Telling them
# apart turns the login form into a tool for discovering which email addresses are
# registered.
_BAD_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password.",
)


async def _issue(user: User, settings: Settings) -> TokenResponse:
    token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        secret=settings.jwt_secret,
        expires_minutes=settings.jwt_expiry_minutes,
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expiry_minutes * 60,
        role=user.role,
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register as a commuter",
)
async def register(
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    try:
        password_hash = hash_password(body.password)
    except PasswordTooLongError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    user = User(
        email=body.email.lower(),
        password_hash=password_hash,
        display_name=body.display_name.strip(),
        role=UserRole.COMMUTER,   # not negotiable, and not accepted from the request
    )
    session.add(user)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # The email uniqueness constraint is enforced by the database rather than by
        # a prior SELECT, because two simultaneous registrations would both pass the
        # SELECT and one would still have to fail here.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that email already exists."
        ) from None

    await session.refresh(user)
    return await _issue(user, settings)


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for a token")
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == body.email.lower()))

    # Verify against a real hash even when the account does not exist, so that a
    # missing account and a wrong password take the same time. Skipping the hash for
    # unknown emails leaks account existence through response timing alone.
    stored = user.password_hash if user else _DUMMY_HASH
    matched = verify_password(body.password, stored)

    if user is None or not matched or not user.is_active:
        raise _BAD_CREDENTIALS

    return await _issue(user, settings)


@router.get("/me", response_model=UserResponse, summary="The current user")
async def me(user: CurrentUser) -> User:
    return user


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a privileged account (admin only)",
)
async def create_user(
    body: UserCreateByAdmin,
    _admin: AdminOnly,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """The only route by which a warden, officer or admin account comes into being."""
    try:
        password_hash = hash_password(body.password)
    except PasswordTooLongError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    user = User(
        email=body.email.lower(),
        password_hash=password_hash,
        display_name=body.display_name.strip(),
        role=body.role,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that email already exists."
        ) from None

    await session.refresh(user)
    return user


@router.get("/users", response_model=list[UserResponse], summary="List accounts (admin only)")
async def list_users(
    _admin: AdminOnly,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 100,
) -> list[User]:
    result = await session.scalars(
        select(User).order_by(User.created_at.desc()).limit(min(limit, 500))
    )
    return list(result)


# Computed once at import. A valid bcrypt hash of a value nothing will ever match,
# used purely to keep failed-login timing constant.
_DUMMY_HASH = hash_password("nkwanta-timing-equalisation-placeholder")
