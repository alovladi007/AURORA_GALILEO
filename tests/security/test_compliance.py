"""
Security and Policy Unit Tests
Comprehensive test suite for compliance module security and policy enforcement.
"""

import unittest
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import pytest

try:
    import cryptography.exceptions  # noqa: F401
except BaseException:  # pyo3 PanicException is not an Exception subclass
    pytest.skip(
        "cryptography native bindings unavailable/broken in this "
        "environment (pyo3 panic on import)",
        allow_module_level=True,
    )

from compliance.authorization import (
    AuthorizationManager, Policy, Permission
)
from compliance.audit import (
    AuditLogger, AuditEvent, AuditEventType, AuditSeverity
)
from compliance.secrets import (
    SecretsManager, SecretType, SecretStatus
)
from compliance.retention import (
    DataRetentionManager, DataClassification, LegalHold, RetentionAction, LegalHoldStatus
)


class TestAuthorizationPolicies(unittest.TestCase):
    """Test authorization and policy enforcement"""
    
    def setUp(self):
        self.auth_manager = AuthorizationManager()
    
    def test_default_policies_loaded(self):
        """Test that default policies are initialized"""
        self.assertIn("research_restricted", self.auth_manager.policies)
        self.assertIn("data_protection", self.auth_manager.policies)
        self.assertIn("compliance_officer", self.auth_manager.policies)
    
    def test_policy_creation(self):
        """Test creating custom policy"""
        policy = Policy(
            name="test_policy",
            description="Test policy",
            permissions={Permission.DATA_READ},
        )
        
        result = self.auth_manager.add_policy(policy)
        self.assertTrue(result)
        self.assertIn("test_policy", self.auth_manager.policies)
    
    def test_role_assignment(self):
        """Test assigning policy to role"""
        result = self.auth_manager.assign_role_policy("researcher", "research_restricted")
        self.assertTrue(result)
        self.assertIn("research_restricted", self.auth_manager.role_policies["researcher"])
    
    def test_user_role_assignment(self):
        """Test assigning role to user"""
        result = self.auth_manager.assign_user_role("user123", "researcher")
        self.assertTrue(result)
        self.assertIn("researcher", self.auth_manager.user_roles["user123"])
    
    def test_permission_check_granted(self):
        """Test permission check - granted"""
        # Setup
        self.auth_manager.assign_role_policy("researcher", "research_restricted")
        self.auth_manager.assign_user_role("user123", "researcher")
        
        # Test
        has_permission = self.auth_manager.check_permission(
            "user123",
            Permission.RESEARCH_CONDUCT
        )
        self.assertTrue(has_permission)
    
    def test_permission_check_denied(self):
        """Test permission check - denied"""
        # Setup
        self.auth_manager.assign_role_policy("researcher", "read_only")
        self.auth_manager.assign_user_role("user123", "researcher")
        
        # Test
        has_permission = self.auth_manager.check_permission(
            "user123",
            Permission.DATA_DELETE
        )
        self.assertFalse(has_permission)
    
    def test_restricted_topics_blocked(self):
        """Test that prohibited topics are blocked"""
        # Setup
        self.auth_manager.assign_role_policy("researcher", "research_restricted")
        self.auth_manager.assign_user_role("user123", "researcher")
        
        # Test with prohibited topic
        has_permission = self.auth_manager.check_permission(
            "user123",
            Permission.RESEARCH_CONDUCT,
            context={
                "topic": "weapons_development",
                "ethical_review_approved": True,
            }
        )
        self.assertFalse(has_permission)
    
    def test_ethical_review_required(self):
        """Test that ethical review is enforced"""
        # Setup
        self.auth_manager.assign_role_policy("researcher", "research_restricted")
        self.auth_manager.assign_user_role("user123", "researcher")
        
        # Test without ethical review
        has_permission = self.auth_manager.check_permission(
            "user123",
            Permission.RESEARCH_CONDUCT,
            context={
                "topic": "user_behavior",
                "ethical_review_approved": False,
            }
        )
        self.assertFalse(has_permission)
        
        # Test with ethical review
        has_permission = self.auth_manager.check_permission(
            "user123",
            Permission.RESEARCH_CONDUCT,
            context={
                "topic": "user_behavior",
                "ethical_review_approved": True,
                "legal_review_approved": True,
            }
        )
        self.assertTrue(has_permission)
    
    def test_policy_export(self):
        """Test policy export for backup"""
        export = self.auth_manager.export_policies()
        
        self.assertIn("policies", export)
        self.assertIn("role_policies", export)
        self.assertIn("policy_hashes", export)
        self.assertIn("exported_at", export)


class TestAuditLogging(unittest.TestCase):
    """Test audit logging functionality"""
    
    def setUp(self):
        self.audit_logger = AuditLogger()
    
    def test_log_event(self):
        """Test logging a basic event"""
        event = self.audit_logger.log_event(
            event_type=AuditEventType.DATA_ACCESSED,
            action="read_data",
            result="success",
            user_id="user123",
            resource="document_001",
        )
        
        self.assertIsInstance(event, AuditEvent)
        self.assertEqual(event.user_id, "user123")
        self.assertEqual(event.resource, "document_001")
    
    def test_log_access(self):
        """Test logging access events"""
        event = self.audit_logger.log_access(
            user_id="user123",
            resource="secret_data",
            action="read",
            granted=True,
        )
        
        self.assertEqual(event.event_type, AuditEventType.ACCESS_GRANTED)
        self.assertEqual(event.severity, AuditSeverity.INFO)
    
    def test_log_access_denied(self):
        """Test logging denied access"""
        event = self.audit_logger.log_access(
            user_id="user123",
            resource="restricted_data",
            action="delete",
            granted=False,
        )
        
        self.assertEqual(event.event_type, AuditEventType.ACCESS_DENIED)
        self.assertEqual(event.severity, AuditSeverity.WARNING)
    
    def test_log_security_alert(self):
        """Test logging security alerts"""
        event = self.audit_logger.log_security_alert(
            alert_type="unauthorized_access_attempt",
            description="Multiple failed login attempts",
            user_id="attacker123",
        )
        
        self.assertEqual(event.event_type, AuditEventType.SECURITY_ALERT)
        self.assertEqual(event.severity, AuditSeverity.CRITICAL)
    
    def test_audit_chain_integrity(self):
        """Test audit log chain verification"""
        # Log multiple events
        for i in range(5):
            self.audit_logger.log_event(
                event_type=AuditEventType.DATA_ACCESSED,
                action=f"action_{i}",
                result="success",
            )
        
        # Verify chain
        is_valid = self.audit_logger.verify_chain()
        self.assertTrue(is_valid)
    
    def test_query_events(self):
        """Test querying audit events"""
        # Log various events
        self.audit_logger.log_event(
            event_type=AuditEventType.DATA_ACCESSED,
            action="read",
            result="success",
            user_id="user123",
        )
        self.audit_logger.log_event(
            event_type=AuditEventType.DATA_MODIFIED,
            action="write",
            result="success",
            user_id="user456",
        )
        
        # Query by user
        events = self.audit_logger.query_events(user_id="user123")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].user_id, "user123")
        
        # Query by event type
        events = self.audit_logger.query_events(event_type=AuditEventType.DATA_MODIFIED)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, AuditEventType.DATA_MODIFIED)
    
    def test_audit_report_generation(self):
        """Test generating audit reports"""
        # Log some events
        for i in range(10):
            self.audit_logger.log_event(
                event_type=AuditEventType.DATA_ACCESSED,
                action="read",
                result="success",
            )
        
        report = self.audit_logger.generate_audit_report()
        
        self.assertIn("total_events", report)
        self.assertIn("event_types", report)
        self.assertIn("severities", report)
        self.assertEqual(report["total_events"], 10)
    
    def test_compliance_summary(self):
        """Test compliance-focused summary"""
        # Log compliance-relevant events
        self.audit_logger.log_access(
            user_id="user123",
            resource="data",
            action="access",
            granted=False,
        )
        
        summary = self.audit_logger.get_compliance_summary(days=30)
        
        self.assertIn("access_denied_count", summary)
        self.assertIn("security_alerts_count", summary)
        self.assertEqual(summary["access_denied_count"], 1)


class TestSecretsManagement(unittest.TestCase):
    """Test secrets management functionality"""
    
    def setUp(self):
        self.secrets_manager = SecretsManager()
    
    def test_create_secret(self):
        """Test creating a secret"""
        secret = self.secrets_manager.create_secret(
            name="api_key",
            value="secret_value_123",
            secret_type=SecretType.API_KEY,
        )
        
        self.assertIsNotNone(secret.secret_id)
        self.assertEqual(secret.name, "api_key")
        self.assertEqual(secret.status, SecretStatus.ACTIVE)
    
    def test_retrieve_secret(self):
        """Test retrieving and decrypting secret"""
        secret = self.secrets_manager.create_secret(
            name="password",
            value="my_password_123",
            secret_type=SecretType.PASSWORD,
        )
        
        retrieved = self.secrets_manager.get_secret(secret.secret_id)
        self.assertEqual(retrieved, "my_password_123")
    
    def test_secret_encryption(self):
        """Test that secrets are encrypted"""
        secret = self.secrets_manager.create_secret(
            name="token",
            value="plaintext_token",
            secret_type=SecretType.TOKEN,
        )
        
        # Encrypted value should not equal plaintext
        self.assertNotEqual(secret.encrypted_value, b"plaintext_token")
    
    def test_rotate_secret(self):
        """Test secret rotation"""
        secret = self.secrets_manager.create_secret(
            name="rotating_key",
            value="old_value",
            secret_type=SecretType.API_KEY,
        )
        
        success = self.secrets_manager.rotate_secret(
            secret.secret_id,
            "new_value",
        )
        
        self.assertTrue(success)
        
        # Old value should not be accessible
        retrieved = self.secrets_manager.get_secret(secret.secret_id)
        self.assertEqual(retrieved, "new_value")
    
    def test_secret_expiration(self):
        """Test secret expiration"""
        expires_at = datetime.utcnow() - timedelta(days=1)  # Already expired
        
        secret = self.secrets_manager.create_secret(
            name="expired_secret",
            value="value",
            secret_type=SecretType.API_KEY,
            expires_at=expires_at,
        )
        
        # Should not be retrievable
        retrieved = self.secrets_manager.get_secret(secret.secret_id)
        self.assertIsNone(retrieved)
    
    def test_rotation_needed(self):
        """Test detection of secrets needing rotation"""
        # Create secret that needs rotation
        secret = self.secrets_manager.create_secret(
            name="old_key",
            value="value",
            secret_type=SecretType.API_KEY,
            rotation_policy_days=1,  # Very short rotation period
        )
        
        # Manually set updated_at to past
        secret.updated_at = datetime.utcnow() - timedelta(days=2)
        
        needs_rotation = self.secrets_manager.check_rotation_needed()
        self.assertEqual(len(needs_rotation), 1)
    
    def test_delete_secret(self):
        """Test deleting a secret"""
        secret = self.secrets_manager.create_secret(
            name="temp_secret",
            value="temp_value",
            secret_type=SecretType.TOKEN,
        )
        
        success = self.secrets_manager.delete_secret(secret.secret_id)
        self.assertTrue(success)
        
        # Should not be retrievable
        retrieved = self.secrets_manager.get_secret(secret.secret_id)
        self.assertIsNone(retrieved)


class TestDataRetention(unittest.TestCase):
    """Test data retention and legal hold functionality"""
    
    def setUp(self):
        self.retention_manager = DataRetentionManager()
    
    def test_default_policies_exist(self):
        """Test that default retention policies exist"""
        self.assertIn("research_data_7y", self.retention_manager.policies)
        self.assertIn("audit_logs_10y", self.retention_manager.policies)
        self.assertIn("user_data_90d", self.retention_manager.policies)
    
    def test_register_data(self):
        """Test registering data for retention"""
        record = self.retention_manager.register_data(
            resource_type="user_data",
            resource_id="user_123",
            classification=DataClassification.CONFIDENTIAL,
        )
        
        self.assertIsNotNone(record.record_id)
        self.assertIsNotNone(record.retention_policy_id)
        self.assertIsNotNone(record.deletion_scheduled_at)
    
    def test_legal_hold_creation(self):
        """Test creating a legal hold"""
        hold = self.retention_manager.create_legal_hold(
            name="Case 2025-001",
            description="Litigation hold",
            case_number="2025-001",
            custodian="legal_team",
            resources={"doc_001", "doc_002"},
        )
        
        self.assertIsNotNone(hold.hold_id)
        self.assertEqual(hold.status, LegalHoldStatus.ACTIVE)
        self.assertEqual(len(hold.resources), 2)
    
    def test_legal_hold_prevents_deletion(self):
        """Test that legal hold prevents data deletion"""
        # Register data
        record = self.retention_manager.register_data(
            resource_type="user_data",
            resource_id="protected_doc",
            classification=DataClassification.CONFIDENTIAL,
        )
        
        # Apply legal hold
        hold = self.retention_manager.create_legal_hold(
            name="Protection Case",
            description="Hold for litigation",
            case_number="CASE-001",
            custodian="legal",
            resources={"protected_doc"},
        )
        
        # Check if protected
        self.assertTrue(record.is_protected())
    
    def test_release_legal_hold(self):
        """Test releasing a legal hold"""
        hold = self.retention_manager.create_legal_hold(
            name="Temporary Hold",
            description="Short-term hold",
            case_number="TEMP-001",
            custodian="legal",
        )
        
        success = self.retention_manager.release_legal_hold(hold.hold_id)
        self.assertTrue(success)
        self.assertEqual(hold.status, LegalHoldStatus.RELEASED)
    
    def test_retention_policy_application(self):
        """Test that correct retention policy is applied"""
        record = self.retention_manager.register_data(
            resource_type="research_data",
            resource_id="experiment_001",
            classification=DataClassification.REGULATED,
        )
        
        policy = self.retention_manager.policies.get(record.retention_policy_id)
        self.assertIsNotNone(policy)
        self.assertEqual(policy.retention_days, 2555)  # 7 years
    
    def test_get_records_for_deletion(self):
        """Test identifying records ready for deletion"""
        # Create record with past deletion date
        past_date = datetime.utcnow() - timedelta(days=100)
        record = self.retention_manager.register_data(
            resource_type="temp_file",
            resource_id="temp_001",
            classification=DataClassification.INTERNAL,
            created_at=past_date,
        )
        
        # Manually set deletion date to past
        record.deletion_scheduled_at = datetime.utcnow() - timedelta(days=1)
        
        ready_for_deletion = self.retention_manager.get_records_for_deletion()
        self.assertIn(record, ready_for_deletion)
    
    def test_compliance_report(self):
        """Test generating compliance report"""
        # Register some data
        self.retention_manager.register_data(
            resource_type="data1",
            resource_id="id1",
            classification=DataClassification.INTERNAL,
        )
        
        report = self.retention_manager.get_compliance_report()
        
        self.assertIn("total_records", report)
        self.assertIn("protected_records", report)
        self.assertIn("active_legal_holds", report)
        self.assertGreater(report["total_records"], 0)


class TestIntegration(unittest.TestCase):
    """Integration tests across compliance modules"""
    
    def setUp(self):
        self.audit_logger = AuditLogger()
        self.auth_manager = AuthorizationManager()
        self.secrets_manager = SecretsManager(audit_logger=self.audit_logger)
        self.retention_manager = DataRetentionManager(audit_logger=self.audit_logger)
    
    def test_full_access_workflow(self):
        """Test complete access workflow with audit"""
        # Setup authorization
        self.auth_manager.assign_role_policy("user", "data_protection")
        self.auth_manager.assign_user_role("user123", "user")
        
        # Check permission
        has_permission = self.auth_manager.check_permission(
            "user123",
            Permission.DATA_READ,
        )
        
        # Log access
        self.audit_logger.log_access(
            user_id="user123",
            resource="document_001",
            action="read",
            granted=has_permission,
        )
        
        # Verify audit trail
        events = self.audit_logger.query_events(user_id="user123")
        self.assertEqual(len(events), 1)
        self.assertTrue(has_permission)
    
    def test_secrets_with_audit(self):
        """Test secrets management with audit logging"""
        # Create secret
        secret = self.secrets_manager.create_secret(
            name="api_key",
            value="secret_value",
            secret_type=SecretType.API_KEY,
            user_id="admin123",
        )
        
        # Retrieve secret
        value = self.secrets_manager.get_secret(
            secret.secret_id,
            user_id="user123",
        )
        
        # Check audit trail
        events = self.audit_logger.query_events(
            event_type=AuditEventType.SECRET_ACCESSED,
        )
        self.assertGreater(len(events), 0)
    
    def test_retention_with_audit(self):
        """Test data retention with audit logging"""
        # Register data
        record = self.retention_manager.register_data(
            resource_type="user_data",
            resource_id="data_001",
            classification=DataClassification.CONFIDENTIAL,
        )
        
        # Check audit trail
        events = self.audit_logger.query_events(
            event_type=AuditEventType.RETENTION_APPLIED,
        )
        self.assertGreater(len(events), 0)


def run_security_tests():
    """Run all security and compliance tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestAuthorizationPolicies))
    suite.addTests(loader.loadTestsFromTestCase(TestAuditLogging))
    suite.addTests(loader.loadTestsFromTestCase(TestSecretsManagement))
    suite.addTests(loader.loadTestsFromTestCase(TestDataRetention))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_security_tests()
    sys.exit(0 if success else 1)
