"""
Circuit Breaker Tests
====================

Tests the enhanced circuit breaker state machine: CLOSED → OPEN → HALF_OPEN
→ CLOSED transitions, fast-fail behavior, and recovery.
"""

import asyncio
import time

import pytest

from api.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenError,
)


async def _fail():
    raise ValueError("boom")


async def _succeed():
    return "ok"


class TestStateMachine:

    @pytest.mark.asyncio
    async def test_starts_closed(self):
        cb = CircuitBreaker("t1", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker("t2", failure_threshold=3)
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(_fail)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_fast_fails(self):
        cb = CircuitBreaker("t3", failure_threshold=1)
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.OPEN
        # Now calls fail fast without executing the function.
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(_succeed)

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        cb = CircuitBreaker("t4", failure_threshold=1, timeout=1)
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.OPEN
        # Simulate timeout elapse.
        cb.last_failure_time = time.time() - 2
        result = await cb.call(_succeed)
        assert result == "ok"
        # One success in HALF_OPEN (success_threshold default 2) -> still half-open.
        assert cb.state in (CircuitState.HALF_OPEN, CircuitState.CLOSED)

    @pytest.mark.asyncio
    async def test_recovers_to_closed(self):
        cb = CircuitBreaker("t5", failure_threshold=1, timeout=1,
                            success_threshold=2)
        with pytest.raises(ValueError):
            await cb.call(_fail)
        cb.last_failure_time = time.time() - 2
        # Two successes in HALF_OPEN -> CLOSED.
        await cb.call(_succeed)
        await cb.call(_succeed)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        cb = CircuitBreaker("t6", failure_threshold=1, timeout=1,
                            success_threshold=2)
        with pytest.raises(ValueError):
            await cb.call(_fail)
        cb.last_failure_time = time.time() - 2
        # First call transitions to HALF_OPEN; a failure there -> OPEN.
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_get_state(self):
        cb = CircuitBreaker("t7", failure_threshold=2)
        state = cb.get_state()
        assert state["name"] == "t7"
        assert state["state"] == "closed"
        assert "failure_count" in state


class TestSyncFunctions:

    @pytest.mark.asyncio
    async def test_supports_sync_callable(self):
        cb = CircuitBreaker("t8", failure_threshold=2)

        def sync_fn(x):
            return x * 2

        result = await cb.call(sync_fn, 21)
        assert result == 42
