"""
ITBIS — Identity Module: Domain Entities
Pure Python domain objects — no SQLAlchemy, no Pydantic, no framework dependency.
These represent the business concepts, not the database structure.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.modules.identity.domain.enums import PermissionName, RoleName


class Permission:
    """
    A named permission that can be assigned to a role.
    Immutable — permissions are created once and referenced.
    """

    def __init__(self, id: uuid.UUID, name: PermissionName) -> None:
        self._id = id
        self._name = name

    @property
    def id(self) -> uuid.UUID:
        return self._id

    @property
    def name(self) -> PermissionName:
        return self._name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Permission):
            return False
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"<Permission {self._name.value}>"


class Role:
    """
    A named role that holds a set of permissions.
    Users are assigned roles; roles are assigned permissions.
    """

    def __init__(
        self,
        id: uuid.UUID,
        name: RoleName,
        permissions: Optional[list[Permission]] = None,
    ) -> None:
        self._id = id
        self._name = name
        self._permissions: list[Permission] = permissions or []

    @property
    def id(self) -> uuid.UUID:
        return self._id

    @property
    def name(self) -> RoleName:
        return self._name

    @property
    def permissions(self) -> list[Permission]:
        return list(self._permissions)

    def has_permission(self, permission: PermissionName) -> bool:
        """Return True if this role carries the named permission."""
        return any(p.name == permission for p in self._permissions)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Role):
            return False
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"<Role {self._name.value}>"


class User:
    """
    Core user domain entity.

    Security invariants:
    - The hashed_password field stores ONLY bcrypt hashes, never plaintext.
    - Callers must use PasswordService to hash before constructing a User.
    - Plaintext passwords must NEVER appear in any attribute of this class.
    """

    def __init__(
        self,
        id: uuid.UUID,
        username: str,
        email: str,
        hashed_password: str,
        full_name: str = "",
        is_active: bool = True,
        is_verified: bool = False,
        is_superadmin: bool = False,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        last_login_at: Optional[datetime] = None,
        roles: Optional[list[Role]] = None,
    ) -> None:
        self._id = id
        self._username = username.strip().lower()
        self._email = email.strip().lower()
        self._hashed_password = hashed_password
        self._full_name = full_name
        self._is_active = is_active
        self._is_verified = is_verified
        self._is_superadmin = is_superadmin
        self._created_at = created_at or datetime.now(timezone.utc)
        self._updated_at = updated_at or datetime.now(timezone.utc)
        self._last_login_at = last_login_at
        self._roles: list[Role] = roles or []

    # ─── Properties ─────────────────────────────────────────
    @property
    def id(self) -> uuid.UUID:
        return self._id

    @property
    def username(self) -> str:
        return self._username

    @property
    def email(self) -> str:
        return self._email

    @property
    def hashed_password(self) -> str:
        """Returns the bcrypt hash. NEVER returns plaintext."""
        return self._hashed_password

    @property
    def full_name(self) -> str:
        return self._full_name

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def is_verified(self) -> bool:
        return self._is_verified

    @property
    def is_superadmin(self) -> bool:
        return self._is_superadmin

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def last_login_at(self) -> Optional[datetime]:
        return self._last_login_at

    @property
    def roles(self) -> list[Role]:
        return list(self._roles)

    # ─── Business Methods ────────────────────────────────────
    def disable(self) -> None:
        """Deactivate the account. All future logins will be refused."""
        self._is_active = False
        self._updated_at = datetime.now(timezone.utc)

    def enable(self) -> None:
        """Re-activate a previously disabled account."""
        self._is_active = True
        self._updated_at = datetime.now(timezone.utc)

    def mark_login(self) -> None:
        """Record successful login timestamp."""
        self._last_login_at = datetime.now(timezone.utc)
        self._updated_at = datetime.now(timezone.utc)

    def update_password(self, new_hashed_password: str) -> None:
        """
        Replace the stored hash. Caller MUST provide a bcrypt hash.
        NEVER call this with a plaintext password.
        """
        self._hashed_password = new_hashed_password
        self._updated_at = datetime.now(timezone.utc)

    def has_permission(self, permission: PermissionName) -> bool:
        """Return True if any of this user's roles carries the permission."""
        if self._is_superadmin:
            return True
        return any(role.has_permission(permission) for role in self._roles)

    def has_role(self, role_name: RoleName) -> bool:
        """Return True if this user has the named role."""
        return any(role.name == role_name for role in self._roles)

    def assign_role(self, role: Role) -> None:
        """Assign a role to this user if not already assigned."""
        if not self.has_role(role.name):
            self._roles.append(role)
            self._updated_at = datetime.now(timezone.utc)

    def permission_names(self) -> list[str]:
        """Return a flat deduplicated list of permission name strings."""
        seen: set[str] = set()
        result: list[str] = []
        for role in self._roles:
            for perm in role.permissions:
                if perm.name.value not in seen:
                    seen.add(perm.name.value)
                    result.append(perm.name.value)
        return result

    # ─── Equality / Repr ─────────────────────────────────────
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return False
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"<User {self._username} active={self._is_active}>"
