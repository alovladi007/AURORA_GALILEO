"""
Workflow API Routes
===================

REST endpoints for monitoring and managing event-driven workflows.
"""

import logging
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from api.event_orchestrator import get_orchestrator, EventType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


class WorkflowExecutionResponse(BaseModel):
    """Workflow execution status response."""
    execution_id: str
    workflow_name: str
    status: str
    started_at: str
    completed_steps: List[str]
    failed_steps: List[str]
    error: Optional[str] = None


class TriggerWorkflowRequest(BaseModel):
    """Request to manually trigger a workflow."""
    event_type: str
    data: dict


@router.get("/executions", response_model=List[WorkflowExecutionResponse])
async def list_workflow_executions(
    status: Optional[str] = None,
    limit: int = 50,
):
    """List all workflow executions, optionally filtered by status."""
    orchestrator = get_orchestrator()
    executions = orchestrator.list_executions()

    # Filter by status if provided
    if status:
        executions = [e for e in executions if e.status == status]

    # Sort by start time (most recent first)
    executions.sort(key=lambda e: e.started_at, reverse=True)

    # Limit results
    executions = executions[:limit]

    return [
        WorkflowExecutionResponse(
            execution_id=e.execution_id,
            workflow_name=e.workflow_name,
            status=e.status,
            started_at=e.started_at.isoformat(),
            completed_steps=e.completed_steps,
            failed_steps=e.failed_steps,
            error=e.error,
        )
        for e in executions
    ]


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionResponse)
async def get_workflow_execution(execution_id: str):
    """Get details of a specific workflow execution."""
    orchestrator = get_orchestrator()
    execution = orchestrator.get_execution(execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return WorkflowExecutionResponse(
        execution_id=execution.execution_id,
        workflow_name=execution.workflow_name,
        status=execution.status,
        started_at=execution.started_at.isoformat(),
        completed_steps=execution.completed_steps,
        failed_steps=execution.failed_steps,
        error=execution.error,
    )


@router.post("/trigger")
async def trigger_workflow(request: TriggerWorkflowRequest):
    """Manually trigger a workflow by publishing an event."""
    orchestrator = get_orchestrator()

    try:
        event_type = EventType(request.event_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event type: {request.event_type}. "
                   f"Valid types: {[e.value for e in EventType]}"
        )

    await orchestrator.publish_event(event_type, request.data)

    return {
        "message": f"Event {event_type} published",
        "event_type": event_type.value,
        "data": request.data,
    }


@router.get("/workflows")
async def list_registered_workflows():
    """List all registered workflows."""
    orchestrator = get_orchestrator()

    workflows_list = []
    for event_type, workflows in orchestrator.workflows.items():
        for workflow in workflows:
            workflows_list.append({
                "name": workflow.name,
                "trigger_event": event_type.value,
                "description": workflow.description,
                "enabled": workflow.enabled,
                "steps": [
                    {
                        "name": step.name,
                        "service": step.service,
                        "action": step.action,
                    }
                    for step in workflow.steps
                ],
            })

    return {
        "workflows": workflows_list,
        "total": len(workflows_list),
    }


@router.get("/statistics")
async def get_workflow_statistics():
    """Get workflow execution statistics."""
    orchestrator = get_orchestrator()
    executions = orchestrator.list_executions()

    total = len(executions)
    completed = len([e for e in executions if e.status == "completed"])
    failed = len([e for e in executions if e.status == "failed"])
    running = len([e for e in executions if e.status == "running"])

    # Per-workflow stats
    workflow_stats = {}
    for execution in executions:
        name = execution.workflow_name
        if name not in workflow_stats:
            workflow_stats[name] = {"total": 0, "completed": 0, "failed": 0, "running": 0}

        workflow_stats[name]["total"] += 1
        workflow_stats[name][execution.status] += 1

    return {
        "total_executions": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "success_rate": (completed / total * 100) if total > 0 else 0,
        "by_workflow": workflow_stats,
    }
