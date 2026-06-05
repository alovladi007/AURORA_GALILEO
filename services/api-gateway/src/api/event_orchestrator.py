"""
Event-Driven Workflow Orchestrator
===================================

Subscribes to platform events from Kafka and triggers cross-service workflows:
  - data_ingested → trigger ML retraining
  - inversion_completed → notify Control Service for mission re-planning
  - maneuver_executed → update inversion data query bounds
  - model_trained → deploy to prediction service

Workflows are defined declaratively and executed asynchronously.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import Kafka, fall back to in-process events
try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError
    _HAS_KAFKA = True
except ImportError:
    _HAS_KAFKA = False
    logger.info("kafka-python not available; event orchestrator limited to in-process events")


class EventType(str, Enum):
    """Platform event types."""
    DATA_INGESTED = "data_ingested"
    INVERSION_STARTED = "inversion_started"
    INVERSION_COMPLETED = "inversion_completed"
    INVERSION_FAILED = "inversion_failed"
    MODEL_TRAINING_STARTED = "model_training_started"
    MODEL_TRAINED = "model_trained"
    MODEL_TRAINING_FAILED = "model_training_failed"
    MANEUVER_EXECUTED = "maneuver_executed"
    MISSION_PLAN_CREATED = "mission_plan_created"
    SIMULATION_COMPLETED = "simulation_completed"


@dataclass
class WorkflowStep:
    """Single step in a workflow."""
    name: str
    service: str  # e.g., "ml", "inversion", "control"
    action: str   # gRPC method name
    params: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[Callable[[Dict], bool]] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class Workflow:
    """Workflow definition."""
    name: str
    trigger_event: EventType
    steps: List[WorkflowStep]
    enabled: bool = True
    description: str = ""


@dataclass
class WorkflowExecution:
    """Tracks a running workflow execution."""
    workflow_name: str
    execution_id: str
    event_data: Dict[str, Any]
    started_at: datetime
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    status: str = "running"  # running, completed, failed
    error: Optional[str] = None


class EventOrchestrator:
    """Orchestrates cross-service workflows triggered by platform events."""

    def __init__(self, kafka_bootstrap_servers: str = "localhost:9092"):
        self.kafka_servers = kafka_bootstrap_servers
        self.workflows: Dict[EventType, List[Workflow]] = {}
        self.executions: Dict[str, WorkflowExecution] = {}
        self.running = False
        self._in_process_queue: asyncio.Queue = asyncio.Queue()
        self._grpc_stubs: Dict[str, Any] = {}

    def register_grpc_stubs(self, stubs: Dict[str, Any]):
        """Register gRPC service stubs for workflow execution."""
        self._grpc_stubs = stubs

    def register_workflow(self, workflow: Workflow):
        """Register a workflow to be triggered by events."""
        if workflow.trigger_event not in self.workflows:
            self.workflows[workflow.trigger_event] = []
        self.workflows[workflow.trigger_event].append(workflow)
        logger.info(f"Registered workflow '{workflow.name}' for event {workflow.trigger_event}")

    def register_default_workflows(self):
        """Register built-in platform workflows."""

        # Workflow 1: Data ingestion triggers ML retraining
        self.register_workflow(Workflow(
            name="auto_ml_retrain",
            trigger_event=EventType.DATA_INGESTED,
            description="Automatically retrain ML models when new gravity data ingested",
            steps=[
                WorkflowStep(
                    name="check_data_volume",
                    service="data",
                    action="QueryGravity",
                    params={"page_size": 1},
                    condition=lambda event: event.get("records_ingested", 0) > 100,
                ),
                WorkflowStep(
                    name="trigger_training",
                    service="ml",
                    action="TrainModel",
                    params={
                        "model_name": "gravity_predictor",
                        "model_type": "neural_network",
                        "dataset_id": "latest_gravity",
                        "num_epochs": 100,
                    },
                ),
            ],
        ))

        # Workflow 2: Inversion completed triggers mission re-planning
        self.register_workflow(Workflow(
            name="update_mission_after_inversion",
            trigger_event=EventType.INVERSION_COMPLETED,
            description="Update mission plan when gravity field inversion completes",
            steps=[
                WorkflowStep(
                    name="get_inversion_result",
                    service="inversion",
                    action="GetInversionResult",
                    params={},  # job_id from event
                ),
                WorkflowStep(
                    name="notify_control",
                    service="control",
                    action="CreateMissionPlan",
                    params={
                        "name": "Updated Mission Plan",
                        "description": "Re-planned based on inversion results",
                    },
                ),
            ],
        ))

        # Workflow 3: Maneuver executed triggers inversion data refresh
        self.register_workflow(Workflow(
            name="refresh_inversion_after_maneuver",
            trigger_event=EventType.MANEUVER_EXECUTED,
            description="Refresh inversion data query after satellite maneuver",
            steps=[
                WorkflowStep(
                    name="query_updated_telemetry",
                    service="data",
                    action="QueryTelemetry",
                    params={},  # satellite_id from event
                ),
                WorkflowStep(
                    name="start_inversion",
                    service="inversion",
                    action="RunInversion",
                    params={
                        "inversion_type": "tikhonov",
                        "config": {"lambda": "auto", "grid_rows": 12, "grid_cols": 12},
                    },
                ),
            ],
        ))

    async def start(self):
        """Start consuming events and executing workflows."""
        if self.running:
            return

        self.running = True
        self.register_default_workflows()
        logger.info("Event orchestrator started")

        if _HAS_KAFKA:
            # Start Kafka consumer for each event topic
            asyncio.create_task(self._consume_events_kafka())
        else:
            # In-process event queue
            asyncio.create_task(self._consume_events_in_process())

    async def stop(self):
        """Stop the event orchestrator."""
        self.running = False
        logger.info("Event orchestrator stopped")

    async def publish_event(self, event_type: EventType, data: Dict[str, Any]):
        """Publish an event to the in-process queue (for testing/fallback)."""
        await self._in_process_queue.put({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        })

    async def _consume_events_kafka(self):
        """Consume events from Kafka topics."""
        try:
            # Subscribe to all platform event topics
            topics = [
                "galileo.events.data",
                "galileo.events.ml",
                "galileo.events.inversion",
                "galileo.events.control",
            ]

            consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=self.kafka_servers,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='event_orchestrator',
            )
            logger.info(f"Kafka consumer started for event topics: {topics}")

            while self.running:
                msg_pack = consumer.poll(timeout_ms=1000)
                for tp, messages in msg_pack.items():
                    for message in messages:
                        await self._handle_event(message.value)

        except Exception as e:
            logger.error(f"Kafka event consumer error: {e}")

    async def _consume_events_in_process(self):
        """Consume events from in-process queue."""
        logger.info("In-process event consumer started")

        while self.running:
            try:
                event = await asyncio.wait_for(self._in_process_queue.get(), timeout=1.0)
                await self._handle_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"In-process event consumer error: {e}")

    async def _handle_event(self, event: Dict[str, Any]):
        """Handle incoming event and trigger matching workflows."""
        event_type_str = event.get("type")
        if not event_type_str:
            logger.warning("Event missing 'type' field")
            return

        try:
            event_type = EventType(event_type_str)
        except ValueError:
            logger.warning(f"Unknown event type: {event_type_str}")
            return

        logger.info(f"Received event: {event_type} - {event.get('data', {})}")

        # Find and execute matching workflows
        workflows = self.workflows.get(event_type, [])
        for workflow in workflows:
            if workflow.enabled:
                asyncio.create_task(self._execute_workflow(workflow, event.get("data", {})))

    async def _execute_workflow(self, workflow: Workflow, event_data: Dict[str, Any]):
        """Execute a workflow asynchronously."""
        import uuid
        execution_id = f"wf_{uuid.uuid4().hex[:8]}"

        execution = WorkflowExecution(
            workflow_name=workflow.name,
            execution_id=execution_id,
            event_data=event_data,
            started_at=datetime.utcnow(),
        )
        self.executions[execution_id] = execution

        logger.info(f"Executing workflow '{workflow.name}' ({execution_id})")

        try:
            for step in workflow.steps:
                # Check condition
                if step.condition and not step.condition(event_data):
                    logger.info(f"Skipping step '{step.name}' (condition not met)")
                    continue

                # Execute step with retries
                success = False
                for attempt in range(step.max_retries + 1):
                    try:
                        await self._execute_step(step, event_data)
                        execution.completed_steps.append(step.name)
                        logger.info(f"Step '{step.name}' completed")
                        success = True
                        break
                    except Exception as e:
                        logger.error(f"Step '{step.name}' failed (attempt {attempt + 1}): {e}")
                        if attempt < step.max_retries:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            execution.failed_steps.append(step.name)
                            execution.error = str(e)

                if not success:
                    execution.status = "failed"
                    logger.error(f"Workflow '{workflow.name}' failed at step '{step.name}'")
                    return

            execution.status = "completed"
            logger.info(f"Workflow '{workflow.name}' completed successfully")

        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)
            logger.error(f"Workflow '{workflow.name}' failed: {e}")

    async def _execute_step(self, step: WorkflowStep, event_data: Dict[str, Any]):
        """Execute a single workflow step (gRPC call)."""
        stub = self._grpc_stubs.get(step.service)
        if not stub:
            raise ValueError(f"No gRPC stub registered for service '{step.service}'")

        # Merge step params with event data
        params = {**step.params}
        for key, value in event_data.items():
            if key not in params:
                params[key] = value

        # Get the gRPC method
        method = getattr(stub, step.action, None)
        if not method:
            raise AttributeError(f"Service '{step.service}' has no method '{step.action}'")

        # Call the method (this is simplified; real implementation needs proper request building)
        logger.info(f"Calling {step.service}.{step.action} with params: {params}")
        # response = await method(...)  # Actual gRPC call would go here
        await asyncio.sleep(0.1)  # Simulate async work

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get workflow execution status."""
        return self.executions.get(execution_id)

    def list_executions(self) -> List[WorkflowExecution]:
        """List all workflow executions."""
        return list(self.executions.values())


# Global orchestrator instance
_orchestrator: Optional[EventOrchestrator] = None


def get_orchestrator() -> EventOrchestrator:
    """Get or create the global event orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        import os
        kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        _orchestrator = EventOrchestrator(kafka_servers)
    return _orchestrator
