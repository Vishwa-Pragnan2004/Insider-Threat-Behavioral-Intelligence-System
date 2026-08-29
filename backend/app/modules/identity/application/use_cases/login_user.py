"""
ITBIS — Identity Module: Login User Use Case
"""

import uuid

from app.core.config import get_settings
from app.modules.identity.application.dtos import LoginDTO, TokenPairDTO
from app.modules.identity.application.services.audit_service import audit_service
from app.modules.identity.application.services.password_service import password_service
from app.modules.identity.application.services.token_service import token_service
from app.modules.identity.domain.events import LoginFailureEvent, LoginSuccessEvent
from app.modules.identity.domain.exceptions import (
    AccountDisabledError,
    InvalidCredentialsError,
)
from app.modules.identity.domain.repositories import (
    IRefreshTokenStore,
    IUserRepository,
)


class LoginUserUseCase:
    """Handles user authentication and token issuance."""

    def __init__(
        self,
        user_repo: IUserRepository,
        token_store: IRefreshTokenStore,
    ) -> None:
        self.user_repo = user_repo
        self.token_store = token_store
        self.settings = get_settings()

    async def execute(self, dto: LoginDTO) -> TokenPairDTO:
        user = await self.user_repo.get_by_email(dto.email)

        # 1. Verify User Exists
        if not user:
            await audit_service.log_event(
                LoginFailureEvent(
                    username=dto.email,
                    ip_address=dto.ip_address,
                    user_agent=dto.user_agent,
                    failure_reason="User not found",
                )
            )
            raise InvalidCredentialsError("Invalid email or password")

        # 2. Verify Password
        if not password_service.verify(dto.password, user.hashed_password):
            await audit_service.log_event(
                LoginFailureEvent(
                    user_id=user.id,
                    username=user.username,
                    ip_address=dto.ip_address,
                    user_agent=dto.user_agent,
                    failure_reason="Invalid password",
                )
            )
            raise InvalidCredentialsError("Invalid email or password")

        # 3. Verify Active Status
        if not user.is_active:
            await audit_service.log_event(
                LoginFailureEvent(
                    user_id=user.id,
                    username=user.username,
                    ip_address=dto.ip_address,
                    user_agent=dto.user_agent,
                    failure_reason="Account disabled",
                )
            )
            raise AccountDisabledError("Account is disabled")

        # 4. Issue Tokens
        claims = {
            "roles": [r.name.value for r in user.roles],
            "permissions": user.permission_names(),
            "is_superadmin": user.is_superadmin,
        }
        access_token = token_service.create_access_token(str(user.id), claims)

        jti = str(uuid.uuid4())
        refresh_token = token_service.create_refresh_token(str(user.id), jti)

        # 5. Store Refresh Token
        ttl = self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        await self.token_store.store(jti, str(user.id), ttl)

        # 6. Update User Last Login
        user.mark_login()
        await self.user_repo.save(user)

        # 7. Audit
        await audit_service.log_event(
            LoginSuccessEvent(
                user_id=user.id,
                username=user.username,
                ip_address=dto.ip_address,
                user_agent=dto.user_agent,
            )
        )

        return TokenPairDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
