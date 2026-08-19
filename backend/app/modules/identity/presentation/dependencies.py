"""
ITBIS — Identity Module: FastAPI Dependencies
Reusable dependencies for authentication and RBAC.
"""

import uuid
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.application.services.token_service import token_service
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.domain.exceptions import TokenExpiredError, TokenInvalidError
from app.modules.identity.infrastructure.repositories import SQLUserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decodes the JWT and returns the User domain entity.
    Raises 401 if token is missing, invalid, or user doesn't exist.
    """
    try:
        payload = token_service.decode_token(token, expected_type="access")
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_repo = SQLUserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def require_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that ensures the current user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )
    return current_user


def require_permission(required_permission: PermissionName) -> Callable:
    """
    Dependency factory for RBAC.
    Usage: @router.get("/foo", dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))])
    """

    async def _require_permission(
        current_user: User = Depends(require_active_user),
    ) -> User:
        if not current_user.has_permission(required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough privileges. Requires: {required_permission.value}",
            )
        return current_user

    return _require_permission
