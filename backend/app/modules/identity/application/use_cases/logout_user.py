"""
ITBIS — Identity Module: Logout User Use Case
"""

import uuid

from app.modules.identity.application.services.audit_service import audit_service
from app.modules.identity.application.services.token_service import token_service
from app.modules.identity.domain.events import LogoutEvent
from app.modules.identity.domain.exceptions import TokenInvalidError
from app.modules.identity.domain.repositories import IRefreshTokenStore


class LogoutUserUseCase:
    """Handles logging out a user by revoking their refresh token."""

    def __init__(
        self,
        token_store: IRefreshTokenStore,
    ) -> None:
        self.token_store = token_store

    async def execute(self, refresh_token: str) -> None:
        """
        Revokes the provided refresh token.
        Fails silently if token is already expired/invalid to prevent
        information leakage during logout.
        """
        try:
            payload = token_service.decode_token(
                refresh_token, expected_type="refresh"
            )
            user_id_str = payload.get("sub")
            jti = payload.get("jti")

            if jti:
                await self.token_store.revoke(jti)

            if user_id_str:
                await audit_service.log_event(
                    LogoutEvent(
                        user_id=uuid.UUID(user_id_str),
                    )
                )

        except TokenInvalidError:
            pass  # Already invalid, consider it logged out
