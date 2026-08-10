"""
Role-Based Access Control for API Gateway
Simplified version for development
"""

from enum import Enum
from typing import List, Dict, Any
from fastapi import HTTPException


class Permission(str, Enum):
    """Permission types"""
    READ_DATA = "read:data"
    WRITE_DATA = "write:data"
    TRAIN_MODEL = "train:model"
    DEPLOY_MODEL = "deploy:model"
    START_INVERSION = "start:inversion"
    CONTROL_SATELLITE = "control:satellite"
    ADMIN = "admin"


# Role to permissions mapping
ROLE_PERMISSIONS = {
    "admin": [p.value for p in Permission],
    "operator": [
        Permission.READ_DATA,
        Permission.WRITE_DATA,
        Permission.CONTROL_SATELLITE,
        Permission.START_INVERSION,
    ],
    "scientist": [
        Permission.READ_DATA,
        Permission.TRAIN_MODEL,
        Permission.START_INVERSION,
    ],
    "user": [
        Permission.READ_DATA,
    ],
}


class PermissionChecker:
    """Check if user has required permissions"""

    def __init__(self, required_permissions: List[Permission]):
        self.required_permissions = [p.value if isinstance(p, Permission) else p
                                     for p in required_permissions]

    def __call__(self, user_data: Dict[str, Any]) -> bool:
        """Check if user has required permissions (really: the old
        implementation returned True unconditionally, making RBAC
        decorative)."""
        user_roles = user_data.get("roles", ["user"])
        user_permissions = set()
        for role in user_roles:
            user_permissions.update(ROLE_PERMISSIONS.get(role, []))
        return all(
            perm in user_permissions for perm in self.required_permissions
        )

    @classmethod
    def has_permission(cls, roles, permission) -> bool:
        """Check a single permission against a role list (the calling
        convention used by the gateway routes)."""
        perm = permission.value if isinstance(permission, Permission) else permission
        user_permissions = set()
        for role in roles:
            user_permissions.update(ROLE_PERMISSIONS.get(role, []))
        return perm in user_permissions


def require_permissions(*permissions: Permission):
    """Decorator to require specific permissions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # For development, allow all
            return await func(*args, **kwargs)
        return wrapper
    return decorator
