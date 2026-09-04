"""
ITBIS — Identity Module: API Router
Exposes authentication and authorization endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.modules.identity.application.dtos import LoginDTO, RegisterUserDTO, UpdateUserDTO
from app.modules.identity.application.use_cases.get_current_user import (
    GetCurrentUserUseCase,
)
from app.modules.identity.application.use_cases.login_user import LoginUserUseCase
from app.modules.identity.application.use_cases.logout_user import LogoutUserUseCase
from app.modules.identity.application.use_cases.refresh_token import RefreshTokenUseCase
from app.modules.identity.application.use_cases.register_user import RegisterUserUseCase
from app.modules.identity.application.use_cases.update_user import UpdateUserUseCase
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.domain.exceptions import IdentityError
from app.modules.identity.infrastructure.redis_token_store import RedisTokenStore
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)
from app.modules.identity.presentation.dependencies import (
    get_current_user,
    require_active_user,
    require_permission,
)
from app.modules.identity.presentation.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterUserRequest,
    TokenResponse,
    UpdateUserRequest,
    UserProfileResponse,
)

router = APIRouter()


# ─── Auth Endpoints ──────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: RegisterUserRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user and assign the default VIEWER role."""
    user_repo = SQLUserRepository(db)
    role_repo = SQLRoleRepository(db)
    use_case = RegisterUserUseCase(user_repo, role_repo)

    dto = RegisterUserDTO(
        username=payload.username,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )

    try:
        result = await use_case.execute(dto)
        return result
    except IdentityError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login and get tokens",
)
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Authenticate and receive access and refresh tokens."""
    user_repo = SQLUserRepository(db)
    token_store = RedisTokenStore(redis)
    use_case = LoginUserUseCase(user_repo, token_store)

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    dto = LoginDTO(
        email=payload.email,
        password=payload.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    try:
        result = await use_case.execute(dto)
        return result
    except IdentityError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Use a refresh token to get a new access token (and rotate refresh token)."""
    user_repo = SQLUserRepository(db)
    token_store = RedisTokenStore(redis)
    use_case = RefreshTokenUseCase(user_repo, token_store)

    try:
        result = await use_case.execute(payload.refresh_token)
        return result
    except IdentityError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout current user",
)
async def logout(
    payload: RefreshTokenRequest,
    current_user: User = Depends(require_active_user),
    redis=Depends(get_redis),
):
    """Logout by revoking the refresh token."""
    token_store = RedisTokenStore(redis)
    use_case = LogoutUserUseCase(token_store)

    await use_case.execute(payload.refresh_token)


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the profile of the currently authenticated user."""
    user_repo = SQLUserRepository(db)
    use_case = GetCurrentUserUseCase(user_repo)

    try:
        result = await use_case.execute(str(current_user.id))
        return result
    except IdentityError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.patch(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current user profile",
)
async def update_me(
    payload: UpdateUserRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the profile of the currently authenticated user."""
    user_repo = SQLUserRepository(db)
    use_case = UpdateUserUseCase(user_repo)

    dto = UpdateUserDTO(
        full_name=payload.full_name,
        email=payload.email,
    )

    try:
        result = await use_case.execute(str(current_user.id), dto)
        return result
    except IdentityError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ─── Demo Endpoints ──────────────────────────────────────────

@router.get(
    "/demo/protected",
    status_code=status.HTTP_200_OK,
    summary="Demo: simple auth protected",
)
async def demo_protected(
    current_user: User = Depends(require_active_user),
):
    """Demonstrates an endpoint requiring valid authentication."""
    return {"message": f"Hello, {current_user.username}. You are authenticated."}


@router.get(
    "/demo/rbac",
    status_code=status.HTTP_200_OK,
    summary="Demo: RBAC protected",
    dependencies=[Depends(require_permission(PermissionName.ADMIN_READ))],
)
async def demo_rbac(
    current_user: User = Depends(require_active_user),
):
    """Demonstrates an endpoint requiring a specific permission."""
    return {"message": "You have the admin:read permission."}
