"""
Tests for RBAC system
"""

import pytest
from api.rbac import (
    Permission,
    Role,
    PermissionChecker,
    ROLE_PERMISSIONS,
    ROLE_HIERARCHY,
)


class TestPermissionChecker:
    """Test permission checking logic"""

    def test_super_admin_has_all_permissions(self):
        """Super admin should have all permissions"""
        permissions = PermissionChecker.get_user_permissions([Role.SUPER_ADMIN.value])
        # Super admin should have at least most permissions
        assert len(permissions) >= 30
        assert Permission.USER_DELETE in permissions
        assert Permission.SYSTEM_CONFIG in permissions

    def test_viewer_has_only_read_permissions(self):
        """Viewer should only have read permissions"""
        permissions = PermissionChecker.get_user_permissions([Role.VIEWER.value])

        # Should have read permissions
        assert Permission.SIMULATION_READ in permissions
        assert Permission.MODEL_READ in permissions
        assert Permission.DATA_READ in permissions

        # Should NOT have write permissions
        assert Permission.USER_DELETE not in permissions
        assert Permission.MODEL_DELETE not in permissions
        assert Permission.SYSTEM_CONFIG not in permissions

    def test_role_inheritance(self):
        """Admin should inherit permissions from lower roles"""
        admin_perms = PermissionChecker.get_user_permissions([Role.ADMIN.value])
        viewer_perms = PermissionChecker.get_user_permissions([Role.VIEWER.value])

        # All viewer permissions should be in admin
        assert viewer_perms.issubset(admin_perms)

    def test_multiple_roles(self):
        """User with multiple roles should have union of permissions"""
        perms_scientist = PermissionChecker.get_user_permissions([Role.SCIENTIST.value])
        perms_operator = PermissionChecker.get_user_permissions([Role.OPERATOR.value])
        perms_both = PermissionChecker.get_user_permissions([
            Role.SCIENTIST.value, Role.OPERATOR.value
        ])

        # Combined should include both
        assert perms_scientist.issubset(perms_both)
        assert perms_operator.issubset(perms_both)

    def test_has_permission_granted(self):
        """has_permission should return True for granted permission"""
        assert PermissionChecker.has_permission(
            [Role.SCIENTIST.value],
            Permission.MODEL_TRAIN,
        )

    def test_has_permission_denied(self):
        """has_permission should return False for denied permission"""
        assert not PermissionChecker.has_permission(
            [Role.VIEWER.value],
            Permission.USER_DELETE,
        )

    def test_has_any_permission(self):
        """has_any_permission should return True if any permission granted"""
        assert PermissionChecker.has_any_permission(
            [Role.VIEWER.value],
            [Permission.USER_DELETE, Permission.DATA_READ],
        )

        assert not PermissionChecker.has_any_permission(
            [Role.VIEWER.value],
            [Permission.USER_DELETE, Permission.SYSTEM_CONFIG],
        )

    def test_has_all_permissions(self):
        """has_all_permissions should return True only if all granted"""
        assert PermissionChecker.has_all_permissions(
            [Role.ADMIN.value],
            [Permission.USER_CREATE, Permission.USER_READ],
        )

        assert not PermissionChecker.has_all_permissions(
            [Role.VIEWER.value],
            [Permission.DATA_READ, Permission.DATA_WRITE],
        )

    def test_unknown_role(self):
        """Unknown role should return empty permissions"""
        permissions = PermissionChecker.get_user_permissions(["nonexistent_role"])
        assert len(permissions) == 0

    def test_service_role(self):
        """Service role should have limited permissions for service-to-service"""
        permissions = PermissionChecker.get_user_permissions([Role.SERVICE.value])

        assert Permission.MODEL_PREDICT in permissions
        assert Permission.DATA_READ in permissions

        # Service role shouldn't have admin permissions
        assert Permission.USER_DELETE not in permissions
        assert Permission.SYSTEM_CONFIG not in permissions


class TestRoleHierarchy:
    """Test role hierarchy structure"""

    def test_super_admin_inherits_all(self):
        """Super admin should inherit from all roles"""
        assert Role.ADMIN in ROLE_HIERARCHY[Role.SUPER_ADMIN]
        assert Role.VIEWER in ROLE_HIERARCHY[Role.SUPER_ADMIN]

    def test_admin_inherits_lower_roles(self):
        """Admin should inherit from operator, scientist, etc."""
        assert Role.OPERATOR in ROLE_HIERARCHY[Role.ADMIN]
        assert Role.VIEWER in ROLE_HIERARCHY[Role.ADMIN]

    def test_viewer_has_no_inheritance(self):
        """Viewer is the base role, no inheritance"""
        assert Role.VIEWER not in ROLE_HIERARCHY


class TestPermissionMapping:
    """Test role-permission mappings"""

    def test_all_roles_defined(self):
        """All roles should have permissions defined"""
        for role in Role:
            assert role in ROLE_PERMISSIONS, f"Role {role} missing permissions"

    def test_admin_has_user_management(self):
        """Admin role should have user management permissions"""
        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.USER_CREATE in admin_perms
        assert Permission.USER_DELETE in admin_perms

    def test_scientist_has_ml_permissions(self):
        """Scientist role should have ML permissions"""
        scientist_perms = ROLE_PERMISSIONS[Role.SCIENTIST]
        assert Permission.MODEL_TRAIN in scientist_perms
        assert Permission.MODEL_CREATE in scientist_perms


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
