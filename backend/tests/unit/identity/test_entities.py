import pytest
import uuid
from datetime import datetime, timezone
from app.modules.identity.domain.entities import Permission, Role, User
from app.modules.identity.domain.enums import PermissionName, RoleName


def make_user(**kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        hashed_password="$2b$12$fakehash",
        full_name="Test User",
    )
    defaults.update(kwargs)
    return User(**defaults)


def make_role(name=RoleName.VIEWER, perms=None):
    permissions = perms or []
    return Role(id=uuid.uuid4(), name=name, permissions=permissions)


def make_permission(name=PermissionName.ALERTS_READ):
    return Permission(id=uuid.uuid4(), name=name)


class TestUser:
    def test_user_defaults(self):
        user = make_user()
        assert user.is_active is True
        assert user.is_verified is False
        assert user.is_superadmin is False
        assert user.last_login_at is None
        assert user.roles == []

    def test_username_normalised_lowercase(self):
        user = make_user(username="ADMIN")
        assert user.username == "admin"

    def test_email_normalised_lowercase(self):
        user = make_user(email="Admin@Example.COM")
        assert user.email == "admin@example.com"

    def test_disable_and_enable(self):
        user = make_user()
        assert user.is_active is True
        user.disable()
        assert user.is_active is False
        user.enable()
        assert user.is_active is True

    def test_mark_login_sets_timestamp(self):
        user = make_user()
        assert user.last_login_at is None
        user.mark_login()
        assert user.last_login_at is not None

    def test_assign_role(self):
        user = make_user()
        role = make_role(RoleName.SECURITY_ANALYST)
        user.assign_role(role)
        assert user.has_role(RoleName.SECURITY_ANALYST)
        # Assigning same role again should not duplicate
        user.assign_role(role)
        assert len(user.roles) == 1

    def test_has_permission_via_role(self):
        perm = make_permission(PermissionName.ALERTS_READ)
        role = make_role(RoleName.SECURITY_ANALYST, perms=[perm])
        user = make_user()
        user.assign_role(role)
        assert user.has_permission(PermissionName.ALERTS_READ)
        assert not user.has_permission(PermissionName.ADMIN_WRITE)

    def test_superadmin_has_all_permissions(self):
        user = make_user(is_superadmin=True)
        assert user.has_permission(PermissionName.ADMIN_WRITE)
        assert user.has_permission(PermissionName.ALERTS_READ)

    def test_update_password(self):
        user = make_user()
        original_hash = user.hashed_password
        user.update_password("$2b$12$newhash")
        assert user.hashed_password == "$2b$12$newhash"
        assert user.hashed_password != original_hash

    def test_permission_names(self):
        perm1 = make_permission(PermissionName.ALERTS_READ)
        perm2 = make_permission(PermissionName.ALERTS_CREATE)
        role = make_role(RoleName.SECURITY_ANALYST, perms=[perm1, perm2])
        user = make_user()
        user.assign_role(role)
        names = user.permission_names()
        assert PermissionName.ALERTS_READ.value in names
        assert PermissionName.ALERTS_CREATE.value in names

    def test_user_equality(self):
        uid = uuid.uuid4()
        user1 = make_user(id=uid)
        user2 = make_user(id=uid, email="other@example.com")
        assert user1 == user2  # Same UUID = same user


class TestRole:
    def test_role_has_permission(self):
        perm = make_permission(PermissionName.ALERTS_READ)
        role = make_role(perms=[perm])
        assert role.has_permission(PermissionName.ALERTS_READ)
        assert not role.has_permission(PermissionName.ADMIN_WRITE)
