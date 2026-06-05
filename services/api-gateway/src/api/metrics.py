"""
Prometheus Metrics
==================

Metrics collection for monitoring API Gateway performance, service health,
and workflow execution.
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)
from fastapi import Response
import time
import logging

logger = logging.getLogger(__name__)

# Create custom registry
registry = CollectorRegistry()

# ==============================================================================
# HTTP Request Metrics
# ==============================================================================

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    registry=registry,
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently being processed',
    ['method', 'endpoint'],
    registry=registry
)

# ==============================================================================
# gRPC Backend Metrics
# ==============================================================================

grpc_requests_total = Counter(
    'grpc_backend_requests_total',
    'Total gRPC requests to backend services',
    ['service', 'method', 'status'],
    registry=registry
)

grpc_request_duration_seconds = Histogram(
    'grpc_backend_request_duration_seconds',
    'gRPC request latency to backend services',
    ['service', 'method'],
    registry=registry,
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0)
)

grpc_errors_total = Counter(
    'grpc_backend_errors_total',
    'Total gRPC errors from backend services',
    ['service', 'method', 'error_code'],
    registry=registry
)

# ==============================================================================
# WebSocket Metrics
# ==============================================================================

websocket_connections_total = Counter(
    'websocket_connections_total',
    'Total WebSocket connections',
    ['endpoint'],
    registry=registry
)

websocket_connections_active = Gauge(
    'websocket_connections_active',
    'Current active WebSocket connections',
    ['endpoint'],
    registry=registry
)

websocket_messages_sent_total = Counter(
    'websocket_messages_sent_total',
    'Total WebSocket messages sent',
    ['topic'],
    registry=registry
)

websocket_messages_dropped_total = Counter(
    'websocket_messages_dropped_total',
    'Total WebSocket messages dropped due to backpressure',
    ['topic'],
    registry=registry
)

# ==============================================================================
# Workflow Metrics
# ==============================================================================

workflow_executions_total = Counter(
    'workflow_executions_total',
    'Total workflow executions',
    ['workflow_name', 'status'],
    registry=registry
)

workflow_execution_duration_seconds = Histogram(
    'workflow_execution_duration_seconds',
    'Workflow execution duration',
    ['workflow_name'],
    registry=registry,
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)
)

workflow_step_failures_total = Counter(
    'workflow_step_failures_total',
    'Total workflow step failures',
    ['workflow_name', 'step_name'],
    registry=registry
)

# ==============================================================================
# Circuit Breaker Metrics
# ==============================================================================

circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 0.5=half-open)',
    ['name'],
    registry=registry
)

circuit_breaker_failures_total = Counter(
    'circuit_breaker_failures_total',
    'Total circuit breaker failures',
    ['name'],
    registry=registry
)

circuit_breaker_successes_total = Counter(
    'circuit_breaker_successes_total',
    'Total circuit breaker successes',
    ['name'],
    registry=registry
)

# ==============================================================================
# Service Health Metrics
# ==============================================================================

service_health = Gauge(
    'service_health',
    'Backend service health (1=healthy, 0=unhealthy)',
    ['service'],
    registry=registry
)

# ==============================================================================
# System Info
# ==============================================================================

system_info = Info(
    'galileo_api_gateway',
    'GALILEO API Gateway version info',
    registry=registry
)

system_info.info({
    'version': '2.0.0',
    'environment': 'production',
    'platform': 'GALILEO V2.0',
})

# ==============================================================================
# Helper Functions
# ==============================================================================

class MetricsMiddleware:
    """FastAPI middleware for automatic HTTP metrics collection."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method = scope["method"]
        path = scope["path"]

        # Skip metrics endpoint itself
        if path == "/metrics":
            return await self.app(scope, receive, send)

        http_requests_in_progress.labels(method=method, endpoint=path).inc()
        start_time = time.time()

        status_code = 500
        try:
            # Capture status code from response
            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                await send(message)

            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.time() - start_time
            http_requests_in_progress.labels(method=method, endpoint=path).dec()
            http_requests_total.labels(
                method=method,
                endpoint=path,
                status=status_code
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                endpoint=path
            ).observe(duration)


def get_metrics():
    """Generate Prometheus metrics output."""
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST
    )


# ==============================================================================
# Context Managers for gRPC Metrics
# ==============================================================================

class grpc_call_metrics:
    """Context manager for gRPC call metrics."""

    def __init__(self, service: str, method: str):
        self.service = service
        self.method = method
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is None:
            status = "success"
            grpc_requests_total.labels(
                service=self.service,
                method=self.method,
                status=status
            ).inc()
        else:
            status = "error"
            error_code = getattr(exc_val, 'code', lambda: 'UNKNOWN')()
            grpc_errors_total.labels(
                service=self.service,
                method=self.method,
                error_code=str(error_code)
            ).inc()
            grpc_requests_total.labels(
                service=self.service,
                method=self.method,
                status=status
            ).inc()

        grpc_request_duration_seconds.labels(
            service=self.service,
            method=self.method
        ).observe(duration)

        return False  # Don't suppress exceptions


# ==============================================================================
# Metrics Update Functions
# ==============================================================================

def update_service_health(service: str, healthy: bool):
    """Update service health metric."""
    service_health.labels(service=service).set(1 if healthy else 0)


def increment_websocket_connection(endpoint: str):
    """Increment WebSocket connection counters."""
    websocket_connections_total.labels(endpoint=endpoint).inc()
    websocket_connections_active.labels(endpoint=endpoint).inc()


def decrement_websocket_connection(endpoint: str):
    """Decrement active WebSocket connections."""
    websocket_connections_active.labels(endpoint=endpoint).dec()


def increment_websocket_message(topic: str, dropped: bool = False):
    """Increment WebSocket message counters."""
    if dropped:
        websocket_messages_dropped_total.labels(topic=topic).inc()
    else:
        websocket_messages_sent_total.labels(topic=topic).inc()


def record_workflow_execution(workflow_name: str, status: str, duration: float):
    """Record workflow execution metrics."""
    workflow_executions_total.labels(
        workflow_name=workflow_name,
        status=status
    ).inc()
    workflow_execution_duration_seconds.labels(
        workflow_name=workflow_name
    ).observe(duration)


def record_workflow_step_failure(workflow_name: str, step_name: str):
    """Record workflow step failure."""
    workflow_step_failures_total.labels(
        workflow_name=workflow_name,
        step_name=step_name
    ).inc()
