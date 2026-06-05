"""
Event Orchestrator Tests
=======================

Tests workflow registration, event handling, and execution tracking. Uses the
in-process event queue (no Kafka required).
"""

import asyncio

import pytest

from api.event_orchestrator import (
    EventOrchestrator,
    EventType,
    Workflow,
    WorkflowStep,
)


@pytest.mark.asyncio
async def test_register_default_workflows():
    orch = EventOrchestrator()
    orch.register_default_workflows()
    # Three built-in workflows across three trigger events.
    assert EventType.DATA_INGESTED in orch.workflows
    assert EventType.INVERSION_COMPLETED in orch.workflows
    assert EventType.MANEUVER_EXECUTED in orch.workflows


@pytest.mark.asyncio
async def test_register_custom_workflow():
    orch = EventOrchestrator()
    wf = Workflow(
        name="custom",
        trigger_event=EventType.MODEL_TRAINED,
        steps=[WorkflowStep(name="s1", service="ml", action="Predict")],
    )
    orch.register_workflow(wf)
    assert orch.workflows[EventType.MODEL_TRAINED][0].name == "custom"


@pytest.mark.asyncio
async def test_event_triggers_workflow_execution():
    orch = EventOrchestrator()

    executed = asyncio.Event()

    # A workflow with a trivial step that just signals execution.
    async def fake_stub_call(*args, **kwargs):
        executed.set()

    wf = Workflow(
        name="signal",
        trigger_event=EventType.SIMULATION_COMPLETED,
        steps=[WorkflowStep(name="signal_step", service="control", action="Noop")],
    )
    orch.register_workflow(wf)

    # Register a fake stub so _execute_step finds the service.
    class FakeStub:
        def Noop(self, *a, **k):
            return None

    orch.register_grpc_stubs({"control": FakeStub()})

    await orch.start()
    await orch.publish_event(EventType.SIMULATION_COMPLETED, {"mission": "m1"})

    # Give the consumer + workflow a moment to run.
    await asyncio.sleep(0.5)
    await orch.stop()

    # An execution should have been recorded.
    execs = orch.list_executions()
    assert len(execs) >= 1
    assert execs[0].workflow_name == "signal"


@pytest.mark.asyncio
async def test_workflow_condition_skips_step():
    orch = EventOrchestrator()

    wf = Workflow(
        name="conditional",
        trigger_event=EventType.DATA_INGESTED,
        steps=[
            WorkflowStep(
                name="only_if_large",
                service="ml",
                action="TrainModel",
                condition=lambda event: event.get("records_ingested", 0) > 1000,
            ),
        ],
    )
    orch.register_workflow(wf)
    orch.register_grpc_stubs({"ml": object()})

    await orch.start()
    # records_ingested below threshold -> step skipped, workflow completes.
    await orch.publish_event(EventType.DATA_INGESTED, {"records_ingested": 10})
    await asyncio.sleep(0.4)
    await orch.stop()

    execs = [e for e in orch.list_executions() if e.workflow_name == "conditional"]
    assert len(execs) >= 1
    assert execs[0].status == "completed"
    # The conditional step was skipped (not in completed_steps).
    assert "only_if_large" not in execs[0].completed_steps


@pytest.mark.asyncio
async def test_unknown_event_type_ignored():
    orch = EventOrchestrator()
    await orch.start()
    # Publish a raw event with an invalid type via the queue.
    await orch._in_process_queue.put({"type": "not_a_real_event", "data": {}})
    await asyncio.sleep(0.3)
    await orch.stop()
    # No executions recorded for unknown events.
    assert orch.list_executions() == []
