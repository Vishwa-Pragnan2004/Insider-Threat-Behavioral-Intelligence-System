"""
ITBIS — Identity Module: Update User Use Case
"""
import uuid

from app.modules.identity.application.dtos import UpdateUserDTO, UserProfileDTO
from app.modules.identity.domain.exceptions import IdentityError


class UpdateUserUseCase:
    def __init__(self, user_repo):
        self._user_repo = user_repo

    async def execute(self, user_id: str, dto: UpdateUserDTO) -> UserProfileDTO:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise IdentityError(f"Invalid user ID: {user_id}")

        user = await self._user_repo.get_by_id(uid)
        if not user:
            raise IdentityError(f"User {user_id} not found")

        if dto.full_name is not None:
            user._full_name = dto.full_name

        if dto.email is not None:
            user._email = dto.email.lower().strip()

        await self._user_repo.save(user)

        return UserProfileDTO(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=[r.name.value for r in user.roles],
            permissions=user.permission_names(),
            is_superadmin=user.is_superadmin,
        )
