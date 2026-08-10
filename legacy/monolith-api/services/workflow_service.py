"""
Workflow Service for GeoSense Platform API

Provides end-to-end mission workflow orchestration:
- Multi-step pipeline execution (simulation → control → calibration → inversion → ML)
- Celery task chain management and monitoring
- Database persistence for workflow state
- MinIO integration for intermediate/final data products
- Workflow templates for common mission scenarios

This service bridges API endpoints with ops infrastructure.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import json
import pickle
import numpy as np

# Import ops infrastructure
try:
    from ops.worker import celery_app, execute_plan_task
    from ops.models import ProcessingJob, SatelliteObservation, GravityProduct, User
    from ops.minio_client import (
        get_minio_client, upload_to_minio, download_from_minio,
        list_objects, get_presigned_url
    )
    OPS_IMPORTS_AVAILABLE = True
except ImportError as e:
    OPS_IMPORTS_AVAILABLE = False
    print(f"Ops imports not available: {e}")

# Import all services for orchestration
try:
    from api.services import (
        get_simulation_service,
        get_inversion_service,
        get_control_service,
        get_calibration_service,
        get_ml_service,
        get_trade_study_service,
        get_compliance_service
    )
    SERVICES_AVAILABLE = True
except ImportError as e:
    SERVICES_AVAILABLE = False
    print(f"Service imports not available: {e}")


class WorkflowType(Enum):
    """Supported workflow types."""
    FULL_MISSION = "full_mission"  # Complete end-to-end mission
    SIMULATION_ONLY = "simulation_only"  # Just orbit propagation
    INVERSION_PIPELINE = "inversion_pipeline"  # Calibration + inversion + ML
    TRADE_STUDY = "trade_study"  # Design optimization
    COMPLIANCE_AUDIT = "compliance_audit"  # Security/compliance check


class WorkflowStatus(Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowService:
    """
    Service for end-to-end workflow orchestration.

    Coordinates multiple services to execute complete mission pipelines,
    with async task execution, state persistence, and result storage.
    """

    def __init__(self):
        """Initialize workflow service."""
        # Always initialize workflows dictionary
        self.workflows = {}  # In-memory workflow tracking
        self.minio_client = None

        if not OPS_IMPORTS_AVAILABLE:
            print("Warning: Ops infrastructure not available.")
            return

        if not SERVICES_AVAILABLE:
            print("Warning: Service layer not available.")
            return

        # Initialize infrastructure
        self.minio_client = get_minio_client()

    # =================================================================
    # Workflow Templates
    # =================================================================

    def get_workflow_template(self, workflow_type: str) -> Dict[str, Any]:
        """
        Get workflow template definition.

        Args:
            workflow_type: Type of workflow

        Returns:
            Workflow template with steps and configuration
        """
        templates = {
            'full_mission': {
                'name': 'Full End-to-End Mission',
                'description': 'Complete mission from orbit design through gravity inversion',
                'steps': [
                    {'service': 'simulation', 'method': 'propagate_formation', 'description': 'Propagate satellite formation'},
                    {'service': 'control', 'method': 'compute_station_keeping', 'description': 'Compute control maneuvers'},
                    {'service': 'simulation', 'method': 'generate_measurements', 'description': 'Generate range measurements'},
                    {'service': 'calibration', 'method': 'compute_phase_noise_budget', 'description': 'Calibrate measurements'},
                    {'service': 'ml', 'method': 'unet_inference', 'description': 'Denoise with U-Net'},
                    {'service': 'inversion', 'method': 'estimate_gravity', 'description': 'Invert for gravity field'},
                    {'service': 'compliance', 'method': 'log_audit_event', 'description': 'Log completion audit'}
                ],
                'estimated_duration': '30-60 minutes',
                'outputs': ['orbit_states', 'control_plan', 'measurements', 'gravity_field']
            },
            'simulation_only': {
                'name': 'Orbit Simulation',
                'description': 'Propagate satellite orbits with perturbations',
                'steps': [
                    {'service': 'simulation', 'method': 'propagate_formation', 'description': 'Propagate formation'},
                    {'service': 'simulation', 'method': 'compute_baseline_vectors', 'description': 'Compute baselines'}
                ],
                'estimated_duration': '5-10 minutes',
                'outputs': ['orbit_states', 'baseline_vectors']
            },
            'inversion_pipeline': {
                'name': 'Gravity Inversion Pipeline',
                'description': 'Process measurements to gravity field',
                'steps': [
                    {'service': 'calibration', 'method': 'compute_measurement_quality', 'description': 'Quality check'},
                    {'service': 'ml', 'method': 'unet_inference', 'description': 'Denoise measurements'},
                    {'service': 'inversion', 'method': 'estimate_gravity', 'description': 'Gravity inversion'},
                    {'service': 'inversion', 'method': 'validate_results', 'description': 'Validate field'}
                ],
                'estimated_duration': '15-30 minutes',
                'outputs': ['denoised_measurements', 'gravity_field', 'validation_metrics']
            },
            'trade_study': {
                'name': 'Mission Design Trade Study',
                'description': 'Optimize mission parameters',
                'steps': [
                    {'service': 'trade_study', 'method': 'run_baseline_study', 'description': 'Baseline analysis'},
                    {'service': 'trade_study', 'method': 'run_orbit_study', 'description': 'Orbit analysis'},
                    {'service': 'trade_study', 'method': 'run_optical_study', 'description': 'Optical analysis'},
                    {'service': 'trade_study', 'method': 'find_pareto_front', 'description': 'Multi-objective optimization'}
                ],
                'estimated_duration': '10-20 minutes',
                'outputs': ['baseline_results', 'orbit_results', 'optical_results', 'pareto_front']
            },
            'compliance_audit': {
                'name': 'Compliance Audit',
                'description': 'Security and compliance verification',
                'steps': [
                    {'service': 'compliance', 'method': 'query_audit_logs', 'description': 'Query audit logs'},
                    {'service': 'compliance', 'method': 'verify_audit_chain', 'description': 'Verify log integrity'},
                    {'service': 'compliance', 'method': 'list_policies', 'description': 'Check policies'},
                    {'service': 'compliance', 'method': 'list_secrets', 'description': 'Check secrets'}
                ],
                'estimated_duration': '2-5 minutes',
                'outputs': ['audit_logs', 'chain_verification', 'policies', 'secrets']
            }
        }

        return templates.get(workflow_type, {})

    def list_workflow_templates(self) -> Dict[str, Any]:
        """List all available workflow templates."""
        templates = ['full_mission', 'simulation_only', 'inversion_pipeline',
                     'trade_study', 'compliance_audit']

        return {
            'templates': [
                {
                    'type': t,
                    **self.get_workflow_template(t)
                }
                for t in templates
            ],
            'count': len(templates)
        }

    # =================================================================
    # Workflow Execution
    # =================================================================

    def submit_workflow(
        self,
        workflow_type: str,
        parameters: Dict[str, Any],
        user_id: Optional[str] = None,
        priority: int = 5
    ) -> Dict[str, Any]:
        """
        Submit workflow for execution.

        Args:
            workflow_type: Type of workflow to execute
            parameters: Workflow-specific parameters
            user_id: User submitting workflow
            priority: Execution priority (1-10)

        Returns:
            Workflow submission confirmation with ID
        """
        if not OPS_IMPORTS_AVAILABLE:
            raise RuntimeError("Ops infrastructure not available")

        # Get template
        template = self.get_workflow_template(workflow_type)
        if not template:
            raise ValueError(f"Unknown workflow type: {workflow_type}")

        # Generate workflow ID
        workflow_id = f"wf_{workflow_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Create workflow state
        workflow_state = {
            'workflow_id': workflow_id,
            'workflow_type': workflow_type,
            'status': WorkflowStatus.PENDING.value,
            'template': template,
            'parameters': parameters,
            'user_id': user_id,
            'priority': priority,
            'created_at': datetime.utcnow().isoformat(),
            'started_at': None,
            'completed_at': None,
            'current_step': 0,
            'total_steps': len(template['steps']),
            'step_results': [],
            'outputs': {},
            'error': None
        }

        # Store in memory and MinIO
        self.workflows[workflow_id] = workflow_state
        self._save_workflow_state(workflow_id, workflow_state)

        # Log submission
        if SERVICES_AVAILABLE:
            try:
                compliance_service = get_compliance_service()
                compliance_service.log_audit_event(
                    event_type='WORKFLOW_SUBMITTED',
                    action=f'submit_workflow:{workflow_type}',
                    result='success',
                    user_id=user_id,
                    resource=workflow_id,
                    metadata={'priority': priority}
                )
            except Exception as e:
                print(f"Failed to log workflow submission: {e}")

        return {
            'workflow_id': workflow_id,
            'status': workflow_state['status'],
            'estimated_duration': template['estimated_duration'],
            'total_steps': workflow_state['total_steps'],
            'created_at': workflow_state['created_at']
        }

    def execute_workflow(
        self,
        workflow_id: str
    ) -> Dict[str, Any]:
        """
        Execute workflow synchronously (for testing/simple workflows).

        Args:
            workflow_id: Workflow identifier

        Returns:
            Execution result
        """
        if not SERVICES_AVAILABLE:
            raise RuntimeError("Services not available")

        # Get workflow state
        workflow_state = self.workflows.get(workflow_id)
        if not workflow_state:
            # Try loading from MinIO
            workflow_state = self._load_workflow_state(workflow_id)
            if not workflow_state:
                raise ValueError(f"Workflow not found: {workflow_id}")

        # Update status
        workflow_state['status'] = WorkflowStatus.RUNNING.value
        workflow_state['started_at'] = datetime.utcnow().isoformat()
        self._save_workflow_state(workflow_id, workflow_state)

        # Execute steps
        try:
            for i, step in enumerate(workflow_state['template']['steps']):
                workflow_state['current_step'] = i + 1

                # Execute step
                step_result = self._execute_step(
                    step,
                    workflow_state['parameters'],
                    workflow_state['step_results']
                )

                workflow_state['step_results'].append({
                    'step': i + 1,
                    'service': step['service'],
                    'method': step['method'],
                    'description': step['description'],
                    'result': step_result,
                    'completed_at': datetime.utcnow().isoformat()
                })

                # Save intermediate state
                self._save_workflow_state(workflow_id, workflow_state)

            # Mark complete
            workflow_state['status'] = WorkflowStatus.COMPLETED.value
            workflow_state['completed_at'] = datetime.utcnow().isoformat()

            # Extract outputs
            workflow_state['outputs'] = self._extract_outputs(
                workflow_state['template'],
                workflow_state['step_results']
            )

        except Exception as e:
            workflow_state['status'] = WorkflowStatus.FAILED.value
            workflow_state['error'] = str(e)
            workflow_state['completed_at'] = datetime.utcnow().isoformat()

        # Save final state
        self._save_workflow_state(workflow_id, workflow_state)

        return {
            'workflow_id': workflow_id,
            'status': workflow_state['status'],
            'current_step': workflow_state['current_step'],
            'total_steps': workflow_state['total_steps'],
            'outputs': workflow_state.get('outputs', {}),
            'error': workflow_state.get('error'),
            'duration': self._compute_duration(
                workflow_state['started_at'],
                workflow_state['completed_at']
            )
        }

    def _execute_step(
        self,
        step: Dict[str, Any],
        parameters: Dict[str, Any],
        previous_results: List[Dict[str, Any]]
    ) -> Any:
        """Execute a single workflow step."""
        service_name = step['service']
        method_name = step['method']

        # Get service instance
        service_map = {
            'simulation': get_simulation_service,
            'inversion': get_inversion_service,
            'control': get_control_service,
            'calibration': get_calibration_service,
            'ml': get_ml_service,
            'trade_study': get_trade_study_service,
            'compliance': get_compliance_service
        }

        if service_name not in service_map:
            raise ValueError(f"Unknown service: {service_name}")

        service = service_map[service_name]()
        method = getattr(service, method_name)

        # Extract step parameters (from workflow params or previous results)
        step_params = self._extract_step_parameters(
            service_name,
            method_name,
            parameters,
            previous_results
        )

        # Execute method
        return method(**step_params)

    def _extract_step_parameters(
        self,
        service: str,
        method: str,
        workflow_params: Dict[str, Any],
        previous_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract parameters for a specific step."""
        # This is simplified - in production, would have sophisticated parameter mapping
        params = {}

        # Get service-specific params from workflow params
        if service in workflow_params:
            params.update(workflow_params[service])

        # Get method-specific params
        method_key = f"{service}.{method}"
        if method_key in workflow_params:
            params.update(workflow_params[method_key])

        # Chain outputs from previous steps if needed
        if previous_results:
            last_result = previous_results[-1]['result']
            # Simple heuristic: if last result has data we might need, include it
            if isinstance(last_result, dict):
                # Don't blindly merge - could override params
                # In production, would have explicit data flow mapping
                pass

        return params

    def _extract_outputs(
        self,
        template: Dict[str, Any],
        step_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract final outputs from step results."""
        outputs = {}

        # Map each expected output to its source step
        expected_outputs = template.get('outputs', [])

        for i, step_result in enumerate(step_results):
            step_name = f"step_{i+1}_{step_result['service']}"
            outputs[step_name] = {
                'service': step_result['service'],
                'method': step_result['method'],
                'description': step_result['description'],
                'completed_at': step_result['completed_at'],
                'has_data': step_result['result'] is not None
            }

        outputs['expected_outputs'] = expected_outputs
        return outputs

    def _compute_duration(
        self,
        start_time: Optional[str],
        end_time: Optional[str]
    ) -> Optional[str]:
        """Compute duration between timestamps."""
        if not start_time or not end_time:
            return None

        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
        delta = end - start

        return f"{delta.total_seconds():.1f}s"

    # =================================================================
    # Workflow Monitoring
    # =================================================================

    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get current workflow status.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Current workflow state
        """
        # Try in-memory first
        workflow_state = self.workflows.get(workflow_id)

        # Try MinIO if not in memory
        if not workflow_state:
            workflow_state = self._load_workflow_state(workflow_id)

        if not workflow_state:
            raise ValueError(f"Workflow not found: {workflow_id}")

        return {
            'workflow_id': workflow_id,
            'workflow_type': workflow_state['workflow_type'],
            'status': workflow_state['status'],
            'current_step': workflow_state['current_step'],
            'total_steps': workflow_state['total_steps'],
            'progress_percent': (workflow_state['current_step'] / workflow_state['total_steps'] * 100)
                if workflow_state['total_steps'] > 0 else 0,
            'created_at': workflow_state['created_at'],
            'started_at': workflow_state.get('started_at'),
            'completed_at': workflow_state.get('completed_at'),
            'error': workflow_state.get('error')
        }

    def list_workflows(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        List workflows with filters.

        Args:
            user_id: Filter by user
            status: Filter by status
            limit: Maximum results

        Returns:
            List of workflows
        """
        # Get all workflows from memory
        workflows = list(self.workflows.values())

        # Apply filters
        if user_id:
            workflows = [w for w in workflows if w.get('user_id') == user_id]

        if status:
            workflows = [w for w in workflows if w['status'] == status]

        # Sort by creation time (newest first)
        workflows.sort(key=lambda w: w['created_at'], reverse=True)

        # Limit results
        workflows = workflows[:limit]

        return {
            'workflows': [
                {
                    'workflow_id': w['workflow_id'],
                    'workflow_type': w['workflow_type'],
                    'status': w['status'],
                    'current_step': w['current_step'],
                    'total_steps': w['total_steps'],
                    'created_at': w['created_at'],
                    'user_id': w.get('user_id')
                }
                for w in workflows
            ],
            'count': len(workflows),
            'filters': {
                'user_id': user_id,
                'status': status,
                'limit': limit
            }
        }

    def cancel_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """
        Cancel running workflow.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Cancellation confirmation
        """
        workflow_state = self.workflows.get(workflow_id)

        if not workflow_state:
            workflow_state = self._load_workflow_state(workflow_id)

        if not workflow_state:
            raise ValueError(f"Workflow not found: {workflow_id}")

        if workflow_state['status'] in [WorkflowStatus.COMPLETED.value, WorkflowStatus.FAILED.value]:
            raise ValueError(f"Cannot cancel workflow in {workflow_state['status']} state")

        workflow_state['status'] = WorkflowStatus.CANCELLED.value
        workflow_state['completed_at'] = datetime.utcnow().isoformat()

        self._save_workflow_state(workflow_id, workflow_state)

        return {
            'workflow_id': workflow_id,
            'status': workflow_state['status'],
            'cancelled_at': workflow_state['completed_at']
        }

    # =================================================================
    # Data Management
    # =================================================================

    def _save_workflow_state(self, workflow_id: str, state: Dict[str, Any]):
        """Save workflow state to MinIO."""
        if not OPS_IMPORTS_AVAILABLE:
            return

        try:
            # Serialize state
            state_bytes = json.dumps(state, default=str).encode('utf-8')

            # Upload to MinIO
            upload_to_minio(
                self.minio_client,
                bucket='workflows',
                key=f"{workflow_id}/state.json",
                data=state_bytes
            )
        except Exception as e:
            print(f"Failed to save workflow state: {e}")

    def _load_workflow_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Load workflow state from MinIO."""
        if not OPS_IMPORTS_AVAILABLE:
            return None

        try:
            # Download from MinIO
            state_bytes = download_from_minio(
                self.minio_client,
                bucket='workflows',
                key=f"{workflow_id}/state.json"
            )

            if state_bytes:
                return json.loads(state_bytes.decode('utf-8'))
        except Exception as e:
            print(f"Failed to load workflow state: {e}")

        return None

    def get_workflow_outputs(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get workflow output data.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Workflow outputs with data URLs
        """
        workflow_state = self.workflows.get(workflow_id)

        if not workflow_state:
            workflow_state = self._load_workflow_state(workflow_id)

        if not workflow_state:
            raise ValueError(f"Workflow not found: {workflow_id}")

        if workflow_state['status'] != WorkflowStatus.COMPLETED.value:
            raise ValueError(f"Workflow not completed: {workflow_state['status']}")

        # Get output files from MinIO
        if OPS_IMPORTS_AVAILABLE:
            output_files = list_objects(
                self.minio_client,
                bucket='workflows',
                prefix=f"{workflow_id}/outputs/"
            )

            # Generate presigned URLs
            output_urls = {}
            for file_key in output_files:
                file_name = file_key.split('/')[-1]
                url = get_presigned_url(
                    self.minio_client,
                    bucket='workflows',
                    key=file_key,
                    expiry=3600
                )
                output_urls[file_name] = url
        else:
            output_urls = {}

        return {
            'workflow_id': workflow_id,
            'status': workflow_state['status'],
            'outputs': workflow_state.get('outputs', {}),
            'output_files': output_urls,
            'completed_at': workflow_state.get('completed_at')
        }


# Singleton
_workflow_service = None

def get_workflow_service() -> WorkflowService:
    """Get or create workflow service singleton."""
    global _workflow_service
    if _workflow_service is None:
        _workflow_service = WorkflowService()
    return _workflow_service
