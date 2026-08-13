"""Who is calling, and are they allowed to.

Two jobs, deliberately separated:

    get_current_user  -- authentication. Who is this?
    require_role      -- authorisation. May they do this?

Conflating them is how systems end up with a logged-in commuter able to assign a warden.
Every protected route states its required role explicitly, so the permission is visible
at the route rather than buried in a service three layers down.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.models import User, UserRole
from app.security import decode_access_token

# auto_error=False so a missing header produces our own 401 with a useful message
# rather than FastAPI's bare 403, which is the wrong code and tells the caller nothing.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated. Send an Authorization: Bearer <token> header.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None:
        raise _UNAUTHENTICATED

    try:
        claims = decode_access_token(credentials.credentials, settings.jwt_secret)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError:
        # One message for malformed, wrongly signed and tampered tokens alike.
        # Distinguishing them tells an attacker which part of the forgery failed.
        raise _UNAUTHENTICATED from None

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        raise _UNAUTHENTICATED from None

    # The database is consulted on every request rather than trusting the token's
    # claims. A token is a snapshot from up to twelve hours ago; the account may have
    # been deactivated since. Without this a banned account keeps its access until
    # its token happens to expire.
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User | None:
    """Who is calling, if anyone — without requiring it.

    For routes that are open to the public but show more to a signed-in user. The
    incident map is the case: anyone may look, but only an officer is shown the actions
    they could take on it.

    A bad token is treated as no token rather than as an error. On a public route the
    caller gets the public view, which is what they asked for.
    """
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, session, settings)
    except HTTPException:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_role(*allowed: UserRole):
    """Guard a route with the roles permitted to reach it.

        @router.post("/incidents/{id}/assign")
        async def assign(user: Annotated[User, Depends(require_role(UserRole.OFFICER))]):
            ...

    Admins are *not* granted everything automatically. If an admin should be able to
    assign wardens, that route says so. Implicit superuser access is how permission
    systems quietly stop meaning anything.
    """

    async def _guard(user: CurrentUser) -> User:
        if user.role not in allowed:
            names = ", ".join(r.value for r in allowed)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of: {names}. You are a {user.role.value}.",
            )
        return user

    return _guard


# Convenience aliases, so routes read as sentences.
OfficerOnly = Annotated[User, Depends(require_role(UserRole.OFFICER))]
AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]
WardenOnly = Annotated[User, Depends(require_role(UserRole.WARDEN))]
ControlRoom = Annotated[User, Depends(require_role(UserRole.OFFICER, UserRole.ADMIN))]
