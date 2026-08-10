"""
Role-Based Access Control (RBAC) for GALILEO Platform

Comprehensive permission system with:
- Hierarchical roles
- Granular permissions
- Resource-based authorization
- Permission inheritance
- Audit logging
"""

import logging
from enum import Enum
from typing import Set, Dict, List, Optional, Callable
from functools import wraps
from datetime import datetime

from fastapi import Depends, HTTPException, status

logger = logging.getLogger(__name__)


# ============================================================================
# Permission Definitions
# ============================================================================

class Permission(str, Enum):
    """All possible permissions in the system"""

    # User management
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_LIST = "user:list"

    # Role management
    ROLE_CREATE = "role:create"
    ROLE_READ = "role:read"
    ROLE_UPDATE = "role:update"
    ROLE_DELETE = "role:delete"
    ROLE_ASSIGN = "role:assign"

    # API key management
    APIKEY_CREATE = "apikey:create"
    APIKEY_READ = "apikey:read"
    APIKEY_REVOKE = "apikey:revoke"
    APIKEY_LIST = "apikey:list"

    # Simulation
    SIMULATION_CREATE = "simulation:create"
    SIMULATION_READ = "simulation:read"
    SIMULATION_UPDATE = "simulation:update"
    SIMULATION_DELETE = "simulation:delete"
    SIMULATION_EXECUTE = "simulation:execute"

    # ML Models
    MODEL_CREATE = "model:create"
    MODEL_READ = "model:read"
    MODEL_UPDATE = "model:update"
    MODEL_DELETE = "model:delete"
    MODEL_TRAIN = "model:train"
    MODEL_DEPLOY = "model:deploy"
    MODEL_PREDICT = "model:predict"

    # Data
    DATA_READ = "data:read"
    DATA_WRITE = "data:write"
    DATA_DELETE = "data:delete"
    DATA_EXPORT = "data:export"
    DATA_IMPORT = "data:import"

    # Satellite operations
    SATELLITE_VIEW = "satellite:view"
    SATELLITE_CONTROL = "satellite:control"
    SATELLITE_CONFIGURE = "satellite:configure"

    # Workflows
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_EXECUTE = "workflow:execute"
    WORKFLOW_CANCEL = "workflow:cancel"
    WORKFLOW_READ = "workflow:read"

    # System administration
    SYSTEM_CONFIG = "system:config"
    SYSTEM_MONITOR = "system:monitor"
    SYSTEM_BACKUP = "system:backup"
    SYSTEM_RESTORE = "system:restore"
    SYSTEM_AUDIT = "system:audit"

    # Reporting
    REPORT_VIEW = "report:view"
    REPORT_CREATE = "report:create"
    REPORT_EXPORT = "report:export"


# ============================================================================
# Role Definitions
# ============================================================================

class Role(str, Enum):
    """Built-in system roles"""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPERATOR = "operator"
    SCIENTIST = "scientist"
    ANALYST = "analyst"
    VIEWER = "viewer"
    SERVICE = "service"  # For service-to-service auth


# Role -> Permissions mapping
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    # Super Admin - all permissions
    Role.SUPER_ADMIN: set(Permission),

    # Admin - most permissions except super-admin specific
    Role.ADMIN: {
        Permission.USER_CREATE, Permission.USER_READ, Permission.USER_UPDATE,
        Permission.USER_DELETE, Permission.USER_LIST,
        Permission.ROLE_READ, Permission.ROLE_ASSIGN,
        Permission.APIKEY_CREATE, Permission.APIKEY_READ,
        Permission.APIKEY_REVOKE, Permission.APIKEY_LIST,
        Permission.SIMULATION_CREATE, Permission.SIMULATION_READ,
        Permission.SIMULATION_UPDATE, Permission.SIMULATION_DELETE,
        Permission.SIMULATION_EXECUTE,
        Permission.MODEL_CREATE, Permission.MODEL_READ, Permission.MODEL_UPDATE,
        Permission.MODEL_DELETE, Permission.MODEL_TRAIN, Permission.MODEL_DEPLOY,
        Permission.MODEL_PREDICT,
        Permission.DATA_READ, Permission.DATA_WRITE, Permission.DATA_DELETE,
        Permission.DATA_EXPORT, Permission.DATA_IMPORT,
        Permission.SATELLITE_VIEW, Permission.SATELLITE_CONTROL,
        Permission.SATELLITE_CONFIGURE,
        Permission.WORKFLOW_CREATE, Permission.WORKFLOW_EXECUTE,
        Permission.WORKFLOW_CANCEL, Permission.WORKFLOW_READ,
        Permission.SYSTEM_MONITOR, Permission.SYSTEM_BACKUP,
        Permission.SYSTEM_AUDIT,
        Permission.REPORT_VIEW, Permission.REPORT_CREATE, Permission.REPORT_EXPORT,
    },

    # Operator - operational tasks
    Role.OPERATOR: {
        Permission.SIMULATION_CREATE, Permission.SIMULATION_READ,
        Permission.SIMULATION_EXECUTE,
        Permission.MODEL_READ, Permission.MODEL_PREDICT,
        Permission.DATA_READ, Permission.DATA_WRITE,
        Permission.SATELLITE_VIEW, Permission.SATELLITE_CONTROL,
        Permission.WORKFLOW_EXECUTE, Permission.WORKFLOW_READ,
        Permission.SYSTEM_MONITOR,
        Permission.REPORT_VIEW, Permission.REPORT_CREATE,
    },

    # Scientist - research and ML
    Role.SCIENTIST: {
        Permission.SIMULATION_CREATE, Permission.SIMULATION_READ,
        Permission.SIMULATION_UPDATE, Permission.SIMULATION_EXECUTE,
        Permission.MODEL_CREATE, Permission.MODEL_READ, Permission.MODEL_UPDATE,
        Permission.MODEL_TRAIN, Permission.MODEL_PREDICT,
        Permission.DATA_READ, Permission.DATA_WRITE, Permission.DATA_EXPORT,
        Permission.DATA_IMPORT,
        Permission.SATELLITE_VIEW,
        Permission.WORKFLOW_CREATE, Permission.WORKFLOW_EXECUTE,
        Permission.WORKFLOW_READ,
        Permission.REPORT_VIEW, Permission.REPORT_CREATE, Permission.REPORT_EXPORT,
    },

    # Analyst - read and analyze
    Role.ANALYST: {
        Permission.SIMULATION_READ,
        Permission.MODEL_READ, Permission.MODEL_PREDICT,
        Permission.DATA_READ, Permission.DATA_EXPORT,
        Permission.SATELLITE_VIEW,
        Permission.WORKFLOW_READ,
        Permission.REPORT_VIEW, Permission.REPORT_CREATE, Permission.REPORT_EXPORT,
    },

    # Viewer - read only
    Role.VIEWER: {
        Permission.SIMULATION_READ,
        Permission.MODEL_READ,
        Permission.DATA_READ,
        Permission.SATELLITE_VIEW,
        Permission.WORKFLOW_READ,
        Permission.REPORT_VIEW,
    },

    # Service - service-to-service auth
    Role.SERVICE: {
        Permission.MODEL_PREDICT,
        Permission.DATA_READ, Permission.DATA_WRITE,
        Permission.WORKFLOW_EXECUTE,
    },
}


# Role hierarchy (higher roles inherit lower role permissions)
ROLE_HIERARCHY: Dict[Role, List[Role]] = {
    Role.SUPER_ADMIN: [Role.ADMIN, Role.OPERATOR, Role.SCIENTIST, Role.ANALYST, Role.VIEWER],
    Role.ADMIN: [Role.OPERATOR, Role.SCIENTIST, Role.ANALYST, Role.VIEWER],
    Role.OPERATOR: [Role.VIEWER],
    Role.SCIENTIST: [Role.ANALYST, Role.VIEWER],
    Role.ANALYST: [Role.VIEWER],
}


# ============================================================================
# Permission Checker
# ============================================================================

class PermissionChecker:
    """Check user permissions against required permissions"""

    @staticmethod
    def get_user_permissions(roles: List[str]) -> Set[Permission]:
        """
        Get all permissions for given roles (with inheritance).

        Args:
            roles: List of role names

        Returns:
            Set of all permissions
        """
        all_permissions: Set[Permission] = set()

        for role_name in roles:
            try:
                role = Role(role_name)

                # Add role's direct permissions
                if role in ROLE_PERMISSIONS:
                    all_permissions.update(ROLE_PERMISSIONS[role])

                # Add inherited permissions
                if role in ROLE_HIERARCHY:
                    for inherited_role in ROLE_HIERARCHY[role]:
                        if inherited_role in ROLE_PERMISSIONS:
                            all_permissions.update(ROLE_PERMISSIONS[inherited_role])

            except ValueError:
                logger.warning(f"Unknown role: {role_name}")

        return all_permissions

    @staticmethod
    def has_permission(
        user_roles: List[str],
        required_permission: Permission,
    ) -> bool:
        """
        Check if user has required permission.

        Args:
            user_roles: User's roles
            required_permission: Permission to check

        Returns:
            True if user has permission
        """
        user_permissions = PermissionChecker.get_user_permissions(user_roles)
        return required_permission in user_permissions

    @staticmethod
    def has_any_permission(
        user_roles: List[str],
        required_permissions: List[Permission],
    ) -> bool:
        """Check if user has any of the required permissions"""
        user_permissions = PermissionChecker.get_user_permissions(user_roles)
        return any(p in user_permissions for p in required_permissions)

    @staticmethod
    def has_all_permissions(
        user_roles: List[str],
        required_permissions: List[Permission],
    ) -> bool:
        """Check if user has all required permissions"""
        user_permissions = PermissionChecker.get_user_permissions(user_roles)
        return all(p in user_permissions for p in required_permissions)


# ============================================================================
# FastAPI Dependencies
# ============================================================================

def require_permission(permission: Permission):
    """
    Dependency to require specific permission.

    Args:
        permission: Required permission

    Usage:
        @app.get("/admin/users")
        async def list_users(
            user: dict = Depends(require_permission(Permission.USER_LIST))
        ):
            ...
    """
    async def permission_dependency(
        current_user: dict = Depends(get_current_user_with_roles)
    ) -> dict:
        user_roles = current_user.get("roles", [])

        if not PermissionChecker.has_permission(user_roles, permission):
            logger.warning(
                f"Permission denied: user={current_user.get('sub')}, "
                f"required={permission.value}, has_roles={user_roles}"
            )

            # Log to audit
            await log_authorization_event(
                user_id=current_user.get("sub"),
                permission=permission.value,
                granted=False,
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission.value}"
            )

        # Log successful authorization
        await log_authorization_event(
            user_id=current_user.get("sub"),
            permission=permission.value,
            granted=True,
        )

        return current_user

    return permission_dependency


def require_any_permission(*permissions: Permission):
    """Require any of the specified permissions"""
    async def permission_dependency(
        current_user: dict = Depends(get_current_user_with_roles)
    ) -> dict:
        user_roles = current_user.get("roles", [])

        if not PermissionChecker.has_any_permission(user_roles, list(permissions)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {[p.value for p in permissions]}"
            )

        return current_user

    return permission_dependency


def require_all_permissions(*permissions: Permission):
    """Require all of the specified permissions"""
    async def permission_dependency(
        current_user: dict = Depends(get_current_user_with_roles)
    ) -> dict:
        user_roles = current_user.get("roles", [])

        if not PermissionChecker.has_all_permissions(user_roles, list(permissions)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires all of: {[p.value for p in permissions]}"
            )

        return current_user

    return permission_dependency


def require_role(role: Role):
    """Require specific role"""
    async def role_dependency(
        current_user: dict = Depends(get_current_user_with_roles)
    ) -> dict:
        user_roles = current_user.get("roles", [])

        if role.value not in user_roles and Role.SUPER_ADMIN.value not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {role.value}"
            )

        return current_user

    return role_dependency


# Helper to get user (importable, avoids circular imports)
async def get_current_user_with_roles(*args, **kwargs):
    """Wrapper to import auth function lazily"""
    from api.auth_v2 import get_current_user
    return await get_current_user(*args, **kwargs)


# ============================================================================
# Audit Logging
# ============================================================================

async def log_authorization_event(
    user_id: str,
    permission: str,
    granted: bool,
    resource: Optional[str] = None,
) -> None:
    """
    Log authorization event for audit trail.

    Args:
        user_id: User ID
        permission: Permission checked
        granted: Whether access was granted
        resource: Optional resource identifier
    """
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "authorization",
        "user_id": user_id,
        "permission": permission,
        "granted": granted,
        "resource": resource,
    }

    # Log to structured logging
    if granted:
        logger.info(f"AUTH_GRANTED: {event}")
    else:
        logger.warning(f"AUTH_DENIED: {event}")

    # In production, also write to audit database
    # await audit_db.insert(event)


# ============================================================================
# Resource-Based Authorization
# ============================================================================

class ResourceOwner:
    """
    Resource-based authorization.
    Check if user owns or has access to specific resource.
    """

    @staticmethod
    async def can_access_resource(
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str = "read",
    ) -> bool:
        """
        Check if user can access specific resource.

        Args:
            user_id: User ID
            resource_type: Type of resource (simulation, model, etc.)
            resource_id: Resource identifier
            action: Action (read, write, delete)

        Returns:
            True if access allowed
        """
        # In production, this would check database for resource ownership
        # and access control lists

        # Example implementation:
        # resource = await db.query(f"SELECT * FROM {resource_type} WHERE id = ?", resource_id)
        # if resource.owner_id == user_id:
        #     return True
        # if user_id in resource.shared_with:
        #     return True

        return True  # Placeholder


def require_resource_access(resource_type: str, action: str = "read"):
    """
    Dependency to require resource-level access.

    Usage:
        @app.get("/simulations/{sim_id}")
        async def get_simulation(
            sim_id: str,
            _: None = Depends(require_resource_access("simulation", "read"))
        ):
            ...
    """
    async def resource_dependency(
        request,  # Will be filled by FastAPI
        current_user: dict = Depends(get_current_user_with_roles)
    ) -> dict:
        # Extract resource ID from path parameters
        resource_id = request.path_params.get(f"{resource_type}_id")

        if not resource_id:
            return current_user

        # Check access
        can_access = await ResourceOwner.can_access_resource(
            user_id=current_user.get("sub"),
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
        )

        if not can_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to {resource_type}/{resource_id}"
            )

        return current_user

    return resource_dependency
