"""
ITBIS — Identity Module: Database Seeders
Populates initial roles, permissions, and superadmin user on startup.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.identity.application.services.password_service import password_service
from app.modules.identity.domain.entities import Permission, Role, User
from app.modules.identity.domain.enums import ROLE_PERMISSIONS, PermissionName, RoleName
from app.modules.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    UserModel,
)
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)

logger = structlog.get_logger(__name__)


async def seed_identity_module(session: AsyncSession) -> None:
    """
    Seed the database with initial identity data.
    Idempotent: safe to run on every startup.
    """
    logger.info("Starting identity module seeding...")

    # 1. Seed Permissions
    existing_perms_stmt = select(PermissionModel.name)
    existing_perms_result = await session.execute(existing_perms_stmt)
    existing_perm_names = {row for row in existing_perms_result.scalars()}

    for perm_enum in PermissionName:
        if perm_enum not in existing_perm_names:
            new_perm = PermissionModel(name=perm_enum)
            session.add(new_perm)

    await session.flush()

    # Need all permissions loaded for role assignment
    all_perms_stmt = select(PermissionModel)
    all_perms_result = await session.execute(all_perms_stmt)
    perm_models = {p.name: p for p in all_perms_result.scalars()}

    # 2. Seed Roles
    role_repo = SQLRoleRepository(session)
    for role_name, required_perms in ROLE_PERMISSIONS.items():
        role = await role_repo.get_by_name(role_name)
        
        # Build pure domain permissions list
        domain_perms = [
            Permission(id=perm_models[p].id, name=p) for p in required_perms
        ]
        
        if not role:
            # Create new role
            import uuid
            role = Role(id=uuid.uuid4(), name=role_name, permissions=domain_perms)
            await role_repo.save(role)
        else:
            # Update existing role's permissions
            role._permissions = domain_perms
            await role_repo.save(role)

    # 3. Seed Superadmin
    settings = get_settings()
    user_repo = SQLUserRepository(session)
    
    superadmin_email = settings.FIRST_SUPERADMIN_EMAIL
    existing_admin = await user_repo.get_by_email(superadmin_email)
    
    if not existing_admin:
        import uuid
        admin_role = await role_repo.get_by_name(RoleName.ADMIN)
        if admin_role:
            hashed_pw = password_service.hash(settings.FIRST_SUPERADMIN_PASSWORD)
            superadmin = User(
                id=uuid.uuid4(),
                username="admin",
                email=superadmin_email,
                hashed_password=hashed_pw,
                full_name="System Administrator",
                is_active=True,
                is_verified=True,
                is_superadmin=True,
            )
            superadmin.assign_role(admin_role)
            await user_repo.save(superadmin)
            logger.info("Superadmin seeded", email=superadmin_email)

    logger.info("Identity module seeding complete")
