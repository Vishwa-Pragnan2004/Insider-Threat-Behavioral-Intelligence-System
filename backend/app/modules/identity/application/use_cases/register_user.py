"""
ITBIS — Identity Module: Register User Use Case
"""

import uuid

from app.modules.identity.application.dtos import RegisterUserDTO, UserProfileDTO
from app.modules.identity.application.services.audit_service import audit_service
from app.modules.identity.application.services.password_service import password_service
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import RoleName
from app.modules.identity.domain.events import UserRegisteredEvent
from app.modules.identity.domain.exceptions import UserAlreadyExistsError
from app.modules.identity.domain.repositories import IRoleRepository, IUserRepository


class RegisterUserUseCase:
    """Handles new user registration."""

    def __init__(
        self,
        user_repo: IUserRepository,
        role_repo: IRoleRepository,
    ) -> None:
        self.user_repo = user_repo
        self.role_repo = role_repo

    async def execute(self, dto: RegisterUserDTO) -> UserProfileDTO:
        """Execute the registration logic."""
        
        # 1. Check uniqueness
        if await self.user_repo.exists_by_email(dto.email):
            raise UserAlreadyExistsError("Email is already registered")
        if await self.user_repo.exists_by_username(dto.username):
            raise UserAlreadyExistsError("Username is already taken")

        # 2. Hash password (enforces strength)
        hashed_pw = password_service.hash(dto.password)

        # 3. Create Entity
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            username=dto.username,
            email=dto.email,
            hashed_password=hashed_pw,
            full_name=dto.full_name,
            is_active=True,
            is_verified=False,
        )

        # 4. Assign default role (VIEWER)
        viewer_role = await self.role_repo.get_by_name(RoleName.VIEWER)
        if viewer_role:
            user.assign_role(viewer_role)

        # 5. Save
        saved_user = await self.user_repo.save(user)

        # 6. Audit
        await audit_service.log_event(
            UserRegisteredEvent(
                user_id=saved_user.id,
                username=saved_user.username,
                email=saved_user.email,
                assigned_role=RoleName.VIEWER if viewer_role else None,
            )
        )

        return UserProfileDTO(
            id=str(saved_user.id),
            username=saved_user.username,
            email=saved_user.email,
            full_name=saved_user.full_name,
            roles=[r.name.value for r in saved_user.roles],
            permissions=saved_user.permission_names(),
            is_superadmin=saved_user.is_superadmin,
        )
