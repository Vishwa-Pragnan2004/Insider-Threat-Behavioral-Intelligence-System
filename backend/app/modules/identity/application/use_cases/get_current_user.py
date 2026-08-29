"""
ITBIS — Identity Module: Get Current User Use Case
"""

import uuid

from app.modules.identity.application.dtos import UserProfileDTO
from app.modules.identity.domain.exceptions import TokenInvalidError
from app.modules.identity.domain.repositories import IUserRepository


class GetCurrentUserUseCase:
    """Retrieves the profile of the currently authenticated user."""

    def __init__(self, user_repo: IUserRepository) -> None:
        self.user_repo = user_repo

    async def execute(self, user_id_str: str) -> UserProfileDTO:
        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            raise TokenInvalidError("Invalid user ID format in token")

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise TokenInvalidError("User not found")

        return UserProfileDTO(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=[r.name.value for r in user.roles],
            permissions=user.permission_names(),
            is_superadmin=user.is_superadmin,
        )
