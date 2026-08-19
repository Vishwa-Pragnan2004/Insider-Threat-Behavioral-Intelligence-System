"""
ITBIS — Identity Module: Refresh Token Use Case
"""

import uuid

from app.core.config import get_settings
from app.modules.identity.application.dtos import TokenPairDTO
from app.modules.identity.application.services.audit_service import audit_service
from app.modules.identity.application.services.token_service import token_service
from app.modules.identity.domain.events import TokenRefreshEvent
from app.modules.identity.domain.exceptions import (
    AccountDisabledError,
    TokenInvalidError,
    TokenRevokedError,
)
from app.modules.identity.domain.repositories import (
    IRefreshTokenStore,
    IUserRepository,
)


class RefreshTokenUseCase:
    """Handles issuing new access tokens using a valid refresh token."""

    def __init__(
        self,
        user_repo: IUserRepository,
        token_store: IRefreshTokenStore,
    ) -> None:
        self.user_repo = user_repo
        self.token_store = token_store
        self.settings = get_settings()

    async def execute(self, refresh_token: str) -> TokenPairDTO:
        # 1. Decode token
        payload = token_service.decode_token(refresh_token, expected_type="refresh")
        user_id_str = payload.get("sub")
        jti = payload.get("jti")

        if not user_id_str or not jti:
            raise TokenInvalidError("Malformed refresh token")

        user_id = uuid.UUID(user_id_str)

        # 2. Check revocation status
        if not await self.token_store.is_valid(jti):
            raise TokenRevokedError("Refresh token has been revoked")

        # 3. Load user
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise TokenInvalidError("User not found")

        # 4. Verify Active Status
        if not user.is_active:
            raise AccountDisabledError("Account is disabled")

        # 5. Revoke old refresh token (Refresh Token Rotation)
        await self.token_store.revoke(jti)

        # 6. Issue New Tokens
        claims = {
            "roles": [r.name.value for r in user.roles],
            "permissions": user.permission_names(),
            "is_superadmin": user.is_superadmin,
        }
        new_access_token = token_service.create_access_token(str(user.id), claims)

        new_jti = str(uuid.uuid4())
        new_refresh_token = token_service.create_refresh_token(str(user.id), new_jti)

        # 7. Store New Refresh Token
        ttl = self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        await self.token_store.store(new_jti, str(user.id), ttl)

        # 8. Audit
        await audit_service.log_event(
            TokenRefreshEvent(
                user_id=user.id,
                username=user.username,
            )
        )

        return TokenPairDTO(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
