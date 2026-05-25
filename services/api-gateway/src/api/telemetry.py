"""
OpenTelemetry integration for distributed tracing
Simplified version for development
"""

import logging
from typing import Dict, Any, Optional
from contextlib import contextmanager
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def instrument_fastapi(app: FastAPI) -> None:
    """
    Instrument FastAPI app with OpenTelemetry
    Simplified for development - just logs
    """
    logger.info("Telemetry instrumentation initialized (development mode)")


@contextmanager
def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Create a trace span
    Simplified for development - just logs
    """
    logger.debug(f"Span: {name} {attributes or {}}")
    try:
        yield
    finally:
        logger.debug(f"Span complete: {name}")


def add_span_attributes(attributes: Dict[str, Any]) -> None:
    """
    Add attributes to current span
    Simplified for development - just logs
    """
    logger.debug(f"Span attributes: {attributes}")


def get_current_trace_id() -> str:
    """
    Get current trace ID
    Simplified for development - returns dummy ID
    """
    return "dev-trace-id"
