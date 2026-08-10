"""
Compliance Service for GeoSense Platform API

Provides business logic for security and compliance operations:
- Audit logging with cryptographic chaining
- Role-based access control (RBAC) and authorization
- Secrets management with encryption and rotation
- Data retention policies and legal holds

This service bridges API endpoints with compliance modules.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from typing import Dict, List, Optional, Any
from datetime import datetime

# Import compliance modules
try:
    from compliance.audit import AuditLogger, AuditEvent, AuditEventType, AuditSeverity
    from compliance.authorization import AuthorizationManager, Policy, Permission
    from compliance.secrets import SecretsManager, SecretType, SecretStatus
    from compliance.retention import DataRetentionManager, LegalHold, LegalHoldStatus, DataClassification
    COMPLIANCE_IMPORTS_AVAILABLE = True
except ImportError as e:
    COMPLIANCE_IMPORTS_AVAILABLE = False
    print(f"Compliance imports not available: {e}")


class ComplianceService:
    """
    Service for compliance and security operations.

    Provides high-level functions for audit logging, authorization,
    secrets management, and data retention.
    """

    def __init__(self):
        """Initialize compliance service."""
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            print("Warning: Compliance modules not available.")
            return

        # Initialize subsystems
        self.audit_logger = AuditLogger()
        self.authz_manager = AuthorizationManager()
        self.secrets_manager = SecretsManager(audit_logger=self.audit_logger)
        self.retention_manager = DataRetentionManager(audit_logger=self.audit_logger)

    # =================================================================
    # Audit Logging
    # =================================================================

    def log_audit_event(
        self,
        event_type: str,
        action: str,
        result: str,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        severity: str = 'info',
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Log an audit event with cryptographic chaining.

        Args:
            event_type: Type of event (e.g., 'auth.login')
            action: Action performed
            result: Result of action
            user_id: User identifier
            resource: Resource accessed
            severity: Event severity
            metadata: Additional metadata
            ip_address: Client IP address

        Returns:
            Dictionary with event details
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        # Convert string to enum
        event_type_enum = AuditEventType[event_type.upper().replace('.', '_')]
        severity_enum = AuditSeverity[severity.upper()]

        event = self.audit_logger.log_event(
            event_type=event_type_enum,
            action=action,
            result=result,
            user_id=user_id,
            resource=resource,
            severity=severity_enum,
            metadata=metadata,
            ip_address=ip_address
        )

        return event.to_dict()

    def query_audit_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Query audit logs with filters.

        Returns:
            Dictionary with filtered audit events
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        # Convert string event_type to enum if provided
        event_type_enum = None
        if event_type:
            try:
                event_type_enum = AuditEventType[event_type.upper().replace('.', '_')]
            except KeyError:
                pass

        # Convert string severity to enum if provided
        severity_enum = None
        if severity:
            try:
                severity_enum = AuditSeverity[severity.upper()]
            except KeyError:
                pass

        events = self.audit_logger.query_events(
            start_time=start_time,
            end_time=end_time,
            user_id=user_id,
            event_type=event_type_enum,
            severity=severity_enum,
        )

        # Apply limit
        events = events[:limit]

        return {
            'events': [e.to_dict() for e in events],
            'count': len(events),
            'chain_verified': self.audit_logger.verify_chain()
        }

    def verify_audit_chain(self) -> Dict[str, Any]:
        """
        Verify integrity of audit log chain.

        Returns:
            Verification result with details
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        is_valid = self.audit_logger.verify_chain()

        return {
            'chain_valid': is_valid,
            'total_events': len(self.audit_logger.events),
            'last_hash': self.audit_logger.last_hash
        }

    # =================================================================
    # Authorization & RBAC
    # =================================================================

    def create_policy(
        self,
        name: str,
        description: str,
        permissions: List[str],
        resources: Optional[List[str]] = None,
        conditions: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create authorization policy.

        Args:
            name: Policy name
            description: Policy description
            permissions: List of permission strings
            resources: Applicable resources
            conditions: Policy conditions

        Returns:
            Created policy details
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        # Convert string permissions to enum
        perm_enums = {Permission[p.upper().replace(':', '_')] for p in permissions}

        policy = Policy(
            name=name,
            description=description,
            permissions=perm_enums,
            resources=resources or [],
            conditions=conditions or {}
        )

        self.authz_manager.add_policy(policy)

        return policy.to_dict()

    def check_permission(
        self,
        user_id: str,
        permission: str,
        resource: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if user has permission for resource.

        Returns:
            Authorization result
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        perm_enum = Permission[permission.upper().replace(':', '_')]

        has_permission = self.authz_manager.check_permission(
            user_id=user_id,
            permission=perm_enum,
            resource=resource
        )

        # Log authorization event
        self.log_audit_event(
            event_type='ACCESS_GRANTED' if has_permission else 'ACCESS_DENIED',
            action=f'check_permission:{permission}',
            result='granted' if has_permission else 'denied',
            user_id=user_id,
            resource=resource,
            severity='info'
        )

        return {
            'user_id': user_id,
            'permission': permission,
            'resource': resource,
            'authorized': has_permission
        }

    def assign_role(
        self,
        user_id: str,
        role: str
    ) -> Dict[str, Any]:
        """
        Assign role to user.

        Returns:
            Assignment confirmation
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        self.authz_manager.assign_role(user_id, role)

        # Log event
        self.log_audit_event(
            event_type='PERMISSION_CHANGED',
            action=f'assign_role:{role}',
            result='success',
            user_id=user_id,
            metadata={'role': role}
        )

        return {
            'user_id': user_id,
            'role': role,
            'status': 'assigned'
        }

    def list_policies(self) -> Dict[str, Any]:
        """List all authorization policies."""
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        policies = [p.to_dict() for p in self.authz_manager.policies.values()]

        return {
            'policies': policies,
            'count': len(policies)
        }

    # =================================================================
    # Secrets Management
    # =================================================================

    def store_secret(
        self,
        name: str,
        value: str,
        secret_type: str,
        rotation_days: int = 90,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Store encrypted secret with rotation policy.

        Args:
            name: Secret name
            value: Secret value (will be encrypted)
            secret_type: Type of secret
            rotation_days: Days until rotation required
            metadata: Additional metadata

        Returns:
            Secret metadata (without value)
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        secret_type_enum = SecretType[secret_type.upper()]

        secret = self.secrets_manager.store_secret(
            name=name,
            value=value,
            secret_type=secret_type_enum,
            rotation_policy_days=rotation_days,
            metadata=metadata or {}
        )

        # Log event
        self.log_audit_event(
            event_type='SECRET_CREATED',
            action='store_secret',
            result='success',
            resource=secret.secret_id,
            metadata={'name': name, 'type': secret_type}
        )

        return secret.to_dict(include_value=False)

    def retrieve_secret(
        self,
        secret_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve and decrypt secret.

        Returns:
            Secret with decrypted value
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        secret_value = self.secrets_manager.get_secret(secret_id)

        # Log access
        self.log_audit_event(
            event_type='SECRET_ACCESSED',
            action='retrieve_secret',
            result='success',
            user_id=user_id,
            resource=secret_id
        )

        return {
            'secret_id': secret_id,
            'value': secret_value,
            'accessed_at': datetime.utcnow().isoformat()
        }

    def rotate_secret(
        self,
        secret_id: str,
        new_value: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Rotate secret to new value.

        Returns:
            Rotation confirmation
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        result = self.secrets_manager.rotate_secret(secret_id, new_value)

        # Log rotation
        self.log_audit_event(
            event_type='SECRET_ROTATED',
            action='rotate_secret',
            result='success',
            user_id=user_id,
            resource=secret_id
        )

        return {
            'secret_id': secret_id,
            'rotated_at': datetime.utcnow().isoformat(),
            'new_version': result.version
        }

    def list_secrets(self, include_expired: bool = False) -> Dict[str, Any]:
        """List all secrets (metadata only)."""
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        # SecretsManager.list_secrets() doesn't accept include_expired parameter
        # It already returns dictionaries, not Secret objects
        secrets = self.secrets_manager.list_secrets()

        return {
            'secrets': secrets,
            'count': len(secrets)
        }

    # =================================================================
    # Data Retention
    # =================================================================

    def create_retention_policy(
        self,
        name: str,
        description: str,
        retention_days: int,
        action: str,
        classification: str,
        applicable_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create data retention policy.

        Args:
            name: Policy name
            description: Policy description
            retention_days: Days to retain data
            action: Action when expired (delete, archive, review)
            classification: Data classification level
            applicable_types: Data types this applies to

        Returns:
            Created policy details
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        policy = self.retention_manager.create_policy(
            name=name,
            description=description,
            retention_days=retention_days,
            action=action,
            classification=classification,
            applicable_types=applicable_types or []
        )

        # Log policy creation
        self.log_audit_event(
            event_type='POLICY_CREATED',
            action='create_retention_policy',
            result='success',
            metadata={'policy_name': name, 'retention_days': retention_days}
        )

        return policy.to_dict()

    def apply_legal_hold(
        self,
        name: str,
        description: str,
        case_number: str,
        custodian: str,
        resources: List[str]
    ) -> Dict[str, Any]:
        """
        Apply legal hold to prevent data deletion.

        Args:
            name: Hold name
            description: Hold description
            case_number: Legal case number
            custodian: Responsible person
            resources: Resource IDs to hold

        Returns:
            Legal hold details
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        hold = self.retention_manager.apply_legal_hold(
            name=name,
            description=description,
            case_number=case_number,
            custodian=custodian,
            resources=set(resources)
        )

        # Log legal hold
        self.log_audit_event(
            event_type='LEGAL_HOLD_APPLIED',
            action='apply_legal_hold',
            result='success',
            metadata={
                'case_number': case_number,
                'resource_count': len(resources)
            }
        )

        return hold.to_dict()

    def release_legal_hold(
        self,
        hold_id: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Release legal hold.

        Returns:
            Release confirmation
        """
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        self.retention_manager.release_hold(hold_id)

        # Log release
        self.log_audit_event(
            event_type='LEGAL_HOLD_APPLIED',
            action='release_legal_hold',
            result='success',
            user_id=user_id,
            resource=hold_id
        )

        return {
            'hold_id': hold_id,
            'released_at': datetime.utcnow().isoformat(),
            'status': 'released'
        }

    def list_retention_policies(self) -> Dict[str, Any]:
        """List all retention policies."""
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        # DataRetentionManager doesn't have list_policies method
        # Access internal policies dictionary directly
        policies = list(self.retention_manager.policies.values())

        return {
            'policies': [p.to_dict() for p in policies],
            'count': len(policies)
        }

    def list_legal_holds(self, active_only: bool = True) -> Dict[str, Any]:
        """List legal holds."""
        if not COMPLIANCE_IMPORTS_AVAILABLE:
            raise RuntimeError("Compliance modules not available")

        # DataRetentionManager doesn't have list_holds method
        # Access internal legal_holds dictionary and filter if needed
        all_holds = list(self.retention_manager.legal_holds.values())

        if active_only:
            holds = [h for h in all_holds if h.is_active()]
        else:
            holds = all_holds

        return {
            'holds': [h.to_dict() for h in holds],
            'count': len(holds)
        }


# Singleton
_compliance_service = None

def get_compliance_service() -> ComplianceService:
    """Get or create compliance service singleton."""
    global _compliance_service
    if _compliance_service is None:
        _compliance_service = ComplianceService()
    return _compliance_service
