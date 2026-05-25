"""
Circuit Breaker pattern for fault tolerance
Simplified version for development
"""

import time
from typing import Callable, Any
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """Simple circuit breaker implementation"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker"""
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.timeout:
                self.state = "half-open"
                logger.info(f"Circuit breaker {self.name} entering half-open state")
            else:
                logger.warning(f"Circuit breaker {self.name} is open")
                raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is open")

        try:
            result = func(*args, **kwargs)

            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
                logger.info(f"Circuit breaker {self.name} closed")

            return result

        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error(f"Circuit breaker {self.name} opened after {self.failure_count} failures")

            raise


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
