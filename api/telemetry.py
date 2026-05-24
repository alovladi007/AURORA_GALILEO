"""
OpenTelemetry Instrumentation for GALILEO Platform

Distributed tracing across all services with:
- Auto-instrumentation for FastAPI, SQLAlchemy, Redis, Celery
- Custom spans for business logic
- Trace context propagation
- Configurable sampling
- Multiple exporters (Jaeger, OTLP, Zipkin)
"""

import os
import logging
from typing import Optional, Any
from functools import wraps

from opentelemetry import trace, baggage, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace.sampling import (
    TraceIdRatioBased,
    ParentBased,
)
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

SERVICE_NAME_ENV = os.getenv("OTEL_SERVICE_NAME", "galileo-api")
SERVICE_VERSION_ENV = os.getenv("OTEL_SERVICE_VERSION", "2.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Sampling rate (0.0 to 1.0)
TRACE_SAMPLING_RATE = float(os.getenv("OTEL_TRACE_SAMPLING_RATE", "0.1" if ENVIRONMENT == "production" else "1.0"))

# Exporter configuration
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
OTLP_INSECURE = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"

JAEGER_AGENT_HOST = os.getenv("JAEGER_AGENT_HOST", "jaeger")
JAEGER_AGENT_PORT = int(os.getenv("JAEGER_AGENT_PORT", "6831"))


# ============================================================================
# Tracer Setup
# ============================================================================

_tracer: Optional[trace.Tracer] = None


def setup_telemetry(
    service_name: str = SERVICE_NAME_ENV,
    service_version: str = SERVICE_VERSION_ENV,
    sampling_rate: float = TRACE_SAMPLING_RATE,
) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing.

    Args:
        service_name: Service identifier
        service_version: Service version
        sampling_rate: Trace sampling rate (0.0 to 1.0)

    Returns:
        Configured tracer
    """
    global _tracer

    # Create resource with service information
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "environment": ENVIRONMENT,
        "deployment.environment": ENVIRONMENT,
    })

    # Configure sampling
    sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))

    # Create tracer provider
    provider = TracerProvider(resource=resource, sampler=sampler)

    # Configure exporters
    try:
        # OTLP exporter (works with Jaeger 1.35+, OpenTelemetry Collector)
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        otlp_exporter = OTLPSpanExporter(
            endpoint=OTLP_ENDPOINT,
            insecure=OTLP_INSECURE,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info(f"OTLP exporter configured: {OTLP_ENDPOINT}")

    except ImportError:
        logger.warning("OTLP exporter not available, install opentelemetry-exporter-otlp")

    # Console exporter for development
    if ENVIRONMENT == "development":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Set global tracer provider
    trace.set_tracer_provider(provider)

    # Configure propagators (B3 + W3C TraceContext)
    set_global_textmap(
        CompositePropagator([
            TraceContextTextMapPropagator(),
            B3MultiFormat(),
        ])
    )

    # Get tracer
    _tracer = trace.get_tracer(service_name, service_version)

    logger.info(
        f"OpenTelemetry initialized: service={service_name} "
        f"version={service_version} sampling={sampling_rate}"
    )

    return _tracer


def get_tracer() -> trace.Tracer:
    """Get configured tracer"""
    global _tracer
    if _tracer is None:
        _tracer = setup_telemetry()
    return _tracer


# ============================================================================
# Auto-Instrumentation
# ============================================================================

def instrument_fastapi(app):
    """Instrument FastAPI application"""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="health,metrics,docs,openapi.json,redoc",
            tracer_provider=trace.get_tracer_provider(),
        )
        logger.info("FastAPI instrumentation enabled")

    except ImportError:
        logger.warning("FastAPI instrumentation not available")


def instrument_sqlalchemy(engine):
    """Instrument SQLAlchemy engine"""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=trace.get_tracer_provider(),
        )
        logger.info("SQLAlchemy instrumentation enabled")

    except ImportError:
        logger.warning("SQLAlchemy instrumentation not available")


def instrument_redis():
    """Instrument Redis client"""
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument(
            tracer_provider=trace.get_tracer_provider(),
        )
        logger.info("Redis instrumentation enabled")

    except ImportError:
        logger.warning("Redis instrumentation not available")


def instrument_celery():
    """Instrument Celery"""
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument(
            tracer_provider=trace.get_tracer_provider(),
        )
        logger.info("Celery instrumentation enabled")

    except ImportError:
        logger.warning("Celery instrumentation not available")


def instrument_httpx():
    """Instrument HTTPX client"""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(
            tracer_provider=trace.get_tracer_provider(),
        )
        logger.info("HTTPX instrumentation enabled")

    except ImportError:
        logger.warning("HTTPX instrumentation not available")


def instrument_all(app=None, engine=None):
    """Instrument all supported libraries"""
    if app:
        instrument_fastapi(app)
    if engine:
        instrument_sqlalchemy(engine)

    instrument_redis()
    instrument_celery()
    instrument_httpx()


# ============================================================================
# Custom Spans
# ============================================================================

def trace_span(
    name: str,
    attributes: Optional[dict] = None,
    record_exception: bool = True,
):
    """
    Decorator to add custom span around function.

    Usage:
        @trace_span("orbit.propagate", attributes={"component": "simulation"})
        def propagate_orbit(initial_state, duration):
            ...
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                tracer = get_tracer()
                with tracer.start_as_current_span(name) as span:
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, v)
                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(trace.StatusCode.OK)
                        return result
                    except Exception as e:
                        if record_exception:
                            span.record_exception(e)
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                        raise
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                tracer = get_tracer()
                with tracer.start_as_current_span(name) as span:
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, v)
                    try:
                        result = func(*args, **kwargs)
                        span.set_status(trace.StatusCode.OK)
                        return result
                    except Exception as e:
                        if record_exception:
                            span.record_exception(e)
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                        raise
            return sync_wrapper

    return decorator


def add_span_attributes(**attributes: Any) -> None:
    """Add attributes to current span"""
    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[dict] = None) -> None:
    """Add event to current span"""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.add_event(name, attributes or {})


def get_current_trace_id() -> Optional[str]:
    """Get current trace ID for correlation"""
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        if ctx.is_valid:
            return format(ctx.trace_id, "032x")
    return None


def get_current_span_id() -> Optional[str]:
    """Get current span ID"""
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        if ctx.is_valid:
            return format(ctx.span_id, "016x")
    return None


# ============================================================================
# Baggage (Cross-Service Context)
# ============================================================================

def set_baggage(key: str, value: str) -> None:
    """Set baggage value to propagate across services"""
    ctx = baggage.set_baggage(key, value)
    context.attach(ctx)


def get_baggage(key: str) -> Optional[str]:
    """Get baggage value"""
    return baggage.get_baggage(key)


# ============================================================================
# Helper functions
# ============================================================================

import asyncio  # For trace_span decorator


def trace_request_context(request) -> dict:
    """
    Extract trace context from request for correlation.

    Returns dict with trace_id, span_id, correlation_id
    """
    return {
        "trace_id": get_current_trace_id(),
        "span_id": get_current_span_id(),
        "correlation_id": request.headers.get("X-Correlation-ID"),
    }


# ============================================================================
# Initialization Helper
# ============================================================================

def initialize_telemetry(app=None, engine=None) -> trace.Tracer:
    """
    One-shot initialization for telemetry.

    Args:
        app: FastAPI app instance
        engine: SQLAlchemy engine

    Returns:
        Configured tracer
    """
    tracer = setup_telemetry()
    instrument_all(app=app, engine=engine)
    return tracer
