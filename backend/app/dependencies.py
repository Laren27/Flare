"""FastAPI dependencies: current user resolution and role checking.

This is wiring, not logic -- the token work lives in `app.services.auth`.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserRole
from app.services import auth as auth_service

# auto_error=False so a missing header produces our own 401 with a
# WWW-Authenticate challenge rather than a bare 403 from the security scheme.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    if credentials is None:
        raise _UNAUTHENTICATED

    try:
        claims = auth_service.decode_access_token(credentials.credentials)
    except auth_service.InvalidToken:
        raise _UNAUTHENTICATED from None

    # The role is re-read from the database rather than trusted from the token:
    # a role changed after issuance must take effect without waiting out the
    # token's expiry.
    user = await auth_service.get_user(session, claims.user_id)
    if user is None:
        raise _UNAUTHENTICATED

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed: UserRole):
    """Dependency factory gating an endpoint on the caller's role.

    Usage: `dependencies=[Depends(require_role(UserRole.ADMIN))]`
    """

    async def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this operation",
            )
        return user

    return dependency
