"""
Unit tests for CircuitBreaker.
"""
from __future__ import annotations
import asyncio

import pytest

from src.circuit_breaker import CircuitBreaker, CircuitState
from src.exceptions import CircuitOpenError


async def _ok() -> str:
    return "ok"


async def _fail() -> None:
    raise RuntimeError("network error")


class TestCircuitBreaker:

    @pytest.mark.asyncio
    async def test_starts_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_successful_call_stays_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)
        result = await cb.call(_ok)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_fail)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_raises_circuit_open_error(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)
        with pytest.raises(RuntimeError):
            await cb.call(_fail)
        with pytest.raises(CircuitOpenError):
            await cb.call(_ok)

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)
        with pytest.raises(RuntimeError):
            await cb.call(_fail)
        with pytest.raises(RuntimeError):
            await cb.call(_fail)
        # Success resets the counter
        await cb.call(_ok)
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0)
        with pytest.raises(RuntimeError):
            await cb.call(_fail)
        assert cb.state == CircuitState.OPEN
        # With recovery_timeout=0 it should immediately allow half-open
        await asyncio.sleep(0.01)
        async with cb._lock:
            cb._maybe_recover()
        assert cb.state == CircuitState.HALF_OPEN
