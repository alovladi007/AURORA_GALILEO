"""
Tests for Circuit Breaker implementation
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from api.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    get_circuit_breaker,
    circuit_breaker,
)


class TestCircuitBreaker:
    """Test circuit breaker state transitions"""

    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        """Circuit should start in CLOSED state"""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Successful call should not affect state"""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        async def success_func():
            return "success"

        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        """Circuit should open after failure threshold reached"""
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=3,
            timeout_seconds=60,
        ))

        async def fail_func():
            raise Exception("test failure")

        # Trigger 3 failures
        for _ in range(3):
            with pytest.raises(Exception):
                await cb.call(fail_func)

        assert cb.state == CircuitState.OPEN
        assert cb.is_open

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_calls(self):
        """Open circuit should reject all calls immediately"""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2))

        async def fail_func():
            raise Exception("test failure")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.call(fail_func)

        # Should now reject without calling function
        async def success_func():
            return "should not be called"

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(success_func)

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """Circuit should transition to HALF_OPEN after timeout"""
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=1,  # 1 second for testing
        ))

        async def fail_func():
            raise Exception("test failure")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.call(fail_func)

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Next successful call should transition to HALF_OPEN
        async def success_func():
            return "success"

        result = await cb.call(success_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_closes_after_success_threshold(self):
        """Circuit should close after success threshold in HALF_OPEN"""
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=1,
        ))

        async def fail_func():
            raise Exception("test failure")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await cb.call(fail_func)

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Two successful calls should close circuit
        async def success_func():
            return "success"

        await cb.call(success_func)
        await cb.call(success_func)

        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_get_state(self):
        """get_state should return current state info"""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        state = cb.get_state()
        assert state["state"] == "closed"
        assert state["failure_count"] == 0


class TestCircuitBreakerDecorator:
    """Test the @circuit_breaker decorator"""

    @pytest.mark.asyncio
    async def test_decorator_basic(self):
        """Decorator should work with async functions"""

        @circuit_breaker("test_decorator", failure_threshold=3)
        async def test_func():
            return "decorated"

        result = await test_func()
        assert result == "decorated"

    @pytest.mark.asyncio
    async def test_decorator_failure_handling(self):
        """Decorator should track failures"""

        call_count = 0

        @circuit_breaker("test_decorator_fail", failure_threshold=2)
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("test")

        # Should fail and open circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await failing_func()

        # Should be rejected without calling
        with pytest.raises(CircuitBreakerOpenError):
            await failing_func()

        assert call_count == 2  # Not 3


class TestGlobalCircuitBreakers:
    """Test global circuit breaker registry"""

    def test_get_or_create(self):
        """get_circuit_breaker should create new or return existing"""
        cb1 = get_circuit_breaker("test_global_1")
        cb2 = get_circuit_breaker("test_global_1")

        # Should be same instance
        assert cb1 is cb2

    def test_different_names(self):
        """Different names should return different instances"""
        cb1 = get_circuit_breaker("test_global_a")
        cb2 = get_circuit_breaker("test_global_b")

        assert cb1 is not cb2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
