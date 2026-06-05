"""
Circuit Breaker pattern for fault tolerance

Enhanced implementation with:
- State machine (closed → open → half-open)
- Prometheus metrics integration
- Async/await support
- Configurable failure thresholds and timeouts
- Success rate monitoring
"""

import time
import asyncio
from typing import Callable, Any, Optional
from functools import wraps
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"           # Normal operation
    OPEN = "open"               # Failures exceeded threshold
    HALF_OPEN = "half-open"     # Testing if service recovered


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """Enhanced circuit breaker with metrics and async support."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: int = 60,
        success_threshold: int = 2,
        expected_exception: type = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.expected_exception = expected_exception

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change = time.time()

        # Update metrics
        self._update_state_metric()

    def _update_state_metric(self):
        """Update Prometheus circuit breaker state metric."""
        try:
            from api.metrics import circuit_breaker_state
            state_values = {
                CircuitState.CLOSED: 0,
                CircuitState.OPEN: 1,
                CircuitState.HALF_OPEN: 0.5,
            }
            circuit_breaker_state.labels(name=self.name).set(state_values[self.state])
        except ImportError:
            pass

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker protection."""
        # Check if should transition from OPEN to HALF_OPEN
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (time.time() - self.last_failure_time >= self.timeout):
                self._transition_to_half_open()
            else:
                logger.warning(f"Circuit breaker {self.name} is OPEN")
                raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")

        try:
            # Execute the function (supports both async and sync)
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            self._on_success()
            return result

        except self.expected_exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call."""
        try:
            from api.metrics import circuit_breaker_successes_total
            circuit_breaker_successes_total.labels(name=self.name).inc()
        except ImportError:
            pass

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self._transition_to_closed()

    def _on_failure(self):
        """Handle failed call."""
        try:
            from api.metrics import circuit_breaker_failures_total
            circuit_breaker_failures_total.labels(name=self.name).inc()
        except ImportError:
            pass

        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Fast fail back to OPEN on any failure in HALF_OPEN state
            self._transition_to_open()
        elif self.failure_count >= self.failure_threshold:
            self._transition_to_open()

    def _transition_to_open(self):
        """Transition to OPEN state."""
        self.state = CircuitState.OPEN
        self.last_state_change = time.time()
        self._update_state_metric()
        logger.error(f"Circuit breaker {self.name} → OPEN (failures: {self.failure_count})")

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self.last_state_change = time.time()
        self._update_state_metric()
        logger.info(f"Circuit breaker {self.name} → HALF_OPEN (testing recovery)")

    def _transition_to_closed(self):
        """Transition to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = time.time()
        self._update_state_metric()
        logger.info(f"Circuit breaker {self.name} → CLOSED (recovered)")

    def get_state(self) -> dict:
        """Get current circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_state_change": self.last_state_change,
            "uptime_seconds": time.time() - self.last_state_change if self.state == CircuitState.CLOSED else 0,
        }


# Global circuit breakers
_circuit_breakers = {}


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    timeout: int = 60
):
    """Decorator for circuit breaker"""
    def decorator(func):
        # Create circuit breaker if it doesn't exist
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                timeout=timeout
            )

        @wraps(func)
        async def wrapper(*args, **kwargs):
            cb = _circuit_breakers[name]
            try:
                return await cb.call(func, *args, **kwargs)
            except CircuitBreakerOpenError:
                # Return fallback response for development
                logger.warning(f"Circuit breaker {name} open, returning fallback")
                return {"error": "Service temporarily unavailable", "circuit_breaker": name}

        return wrapper
    return decorator
