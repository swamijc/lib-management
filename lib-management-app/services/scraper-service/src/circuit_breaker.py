"""
Scraper Service — Circuit Breaker.

States:
  CLOSED   → normal operation (failures counted)
  OPEN     → fast-fail without network call (after failure_threshold exceeded)
  HALF_OPEN → one trial request allowed (after recovery_timeout seconds)
"""
from __future__ import annotations
import asyncio
import time
from enum import Enum
from typing import Any, Callable, Awaitable

from .exceptions import CircuitOpenError


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Per-registry circuit breaker.  Thread-safe via asyncio.Lock."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        """Execute `fn` guarded by the circuit breaker."""
        async with self._lock:
            self._maybe_recover()
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is OPEN — "
                    f"retry after {self._seconds_until_recovery():.0f}s"
                )

        try:
            result = await fn(*args, **kwargs)
            async with self._lock:
                self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            async with self._lock:
                self._on_failure()
            raise

    # ── Internal state machine ──────────────────────────────────────────────

    def _maybe_recover(self) -> None:
        """Transition OPEN → HALF_OPEN after recovery_timeout has elapsed."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN

    def _on_success(self) -> None:
        self._failure_count = 0
        self._opened_at = None
        self._state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()

    def _seconds_until_recovery(self) -> float:
        if self._opened_at is None:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self.recovery_timeout - elapsed)
