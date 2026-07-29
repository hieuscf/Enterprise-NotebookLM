# =============================================================================
# File: circuit_breaker.py
# Module/Service: Core — Resilience
# Layer: Adapter
# Purpose: Generic pybreaker wrapper with logging and per-service metrics.
# Responsibilities:
#   - Closed → Open → Half-Open lifecycle with configurable thresholds
#   - Fail-fast when open; structured logs on state transitions
# Dependencies:
#   - pybreaker, app.core.logging, app.core.resilience.metrics
# Public Exports:
#   - CircuitBreakerConfig, CircuitBreakerOpenError, ResilientCircuitBreaker,
#     build_circuit_breaker
# Database/Table: N/A
# Related Modules: app.clients.llamaparse_client
# Important Notes: One instance per downstream service — never share with LLM providers.
#   Each service supplies its own CircuitBreakerConfig.metrics_prefix (e.g. llamaparse_cb
#   vs anthropic_cb) so state, metrics, and logging namespaces stay isolated.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

import pybreaker
from pybreaker import CircuitBreaker, CircuitBreakerListener, CircuitBreakerState

from app.core.logging import get_logger
from app.core.resilience.metrics import CircuitBreakerMetrics, get_circuit_breaker_metrics

P = ParamSpec("P")
T = TypeVar("T")

logger = get_logger(__name__)

_STATE_OPEN = "open"
_STATE_HALF_OPEN = "half-open"
_STATE_CLOSED = "closed"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit breaker is open."""

    def __init__(self, service_name: str, message: str | None = None) -> None:
        self.service_name = service_name
        super().__init__(message or f"{service_name} circuit breaker open")


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    """Configuration for one isolated circuit breaker instance."""

    name: str
    failure_threshold: int
    reset_timeout_seconds: int
    success_threshold: int
    metrics_prefix: str

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.reset_timeout_seconds < 1:
            raise ValueError("reset_timeout_seconds must be >= 1")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.metrics_prefix.strip():
            raise ValueError("metrics_prefix must not be empty")


class _ObservabilityListener(CircuitBreakerListener):
    """Emit structured logs and counters on breaker lifecycle events."""

    def __init__(self, *, service_name: str, metrics: CircuitBreakerMetrics) -> None:
        self._service_name = service_name
        self._metrics = metrics

    def state_change(
        self,
        cb: CircuitBreaker,
        old_state: CircuitBreakerState | None,
        new_state: CircuitBreakerState,
    ) -> None:
        old_name = _state_name(old_state)
        new_name = _state_name(new_state)
        if new_name == _STATE_OPEN:
            self._metrics.inc_open()
            if old_name in {_STATE_CLOSED, _STATE_HALF_OPEN}:
                self._metrics.inc_trip()
            logger.warning(
                "circuit_breaker_open",
                service_name=self._service_name,
                circuit_breaker=cb.name,
                old_state=old_name,
                new_state=new_name,
            )
            return
        if new_name == _STATE_HALF_OPEN:
            self._metrics.inc_half_open()
            logger.warning(
                "circuit_breaker_half_open",
                service_name=self._service_name,
                circuit_breaker=cb.name,
                old_state=old_name,
                new_state=new_name,
            )
            return
        if new_name == _STATE_CLOSED:
            self._metrics.inc_close()
            logger.info(
                "circuit_breaker_close",
                service_name=self._service_name,
                circuit_breaker=cb.name,
                old_state=old_name,
                new_state=new_name,
            )
            if old_name == _STATE_HALF_OPEN:
                logger.info(
                    "circuit_breaker_recovery_success",
                    service_name=self._service_name,
                    circuit_breaker=cb.name,
                )

    def failure(self, cb: CircuitBreaker, exc: BaseException) -> None:
        logger.warning(
            "circuit_breaker_failure",
            service_name=self._service_name,
            circuit_breaker=cb.name,
            exception=str(exc),
            fail_counter=cb.fail_counter,
        )

    def success(self, cb: CircuitBreaker) -> None:
        if _state_name(cb.state) == _STATE_HALF_OPEN:
            logger.info(
                "circuit_breaker_half_open_success",
                service_name=self._service_name,
                circuit_breaker=cb.name,
                success_counter=cb.success_counter,
                success_threshold=cb.success_threshold,
            )


class ResilientCircuitBreaker:
    """Service-scoped circuit breaker with fail-fast semantics."""

    def __init__(
        self,
        config: CircuitBreakerConfig,
        breaker: CircuitBreaker,
        metrics: CircuitBreakerMetrics,
    ) -> None:
        self._config = config
        self._breaker = breaker
        self._metrics = metrics

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def state(self) -> str:
        return _state_name(self._breaker.state)

    def metrics_snapshot(self) -> dict[str, int]:
        return self._metrics.snapshot()

    def call(self, func: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> T:
        """Invoke ``func`` through the breaker, fail-fast when open."""
        try:
            return self._breaker.call(func, *args, **kwargs)
        except pybreaker.CircuitBreakerError as exc:
            self._metrics.inc_fail_fast()
            logger.warning(
                "circuit_breaker_fail_fast",
                service_name=self._config.name,
                circuit_breaker=self._breaker.name,
                exception=str(exc),
            )
            raise CircuitBreakerOpenError(self._config.name) from exc

    def close(self) -> None:
        """Force the breaker back to closed (tests / admin hooks)."""
        self._breaker.close()


def build_circuit_breaker(
    config: CircuitBreakerConfig,
    *,
    exclude: Iterable[type[BaseException] | Callable[[Any], bool]] = (),
) -> ResilientCircuitBreaker:
    """Construct an isolated circuit breaker for one downstream service."""
    metrics = get_circuit_breaker_metrics(config.metrics_prefix)
    listener = _ObservabilityListener(service_name=config.name, metrics=metrics)
    breaker = CircuitBreaker(
        fail_max=config.failure_threshold,
        reset_timeout=config.reset_timeout_seconds,
        success_threshold=config.success_threshold,
        exclude=tuple(exclude),
        listeners=(listener,),
        name=config.name,
    )
    return ResilientCircuitBreaker(config=config, breaker=breaker, metrics=metrics)


def _state_name(state: CircuitBreakerState | None) -> str:
    if state is None:
        return "unknown"
    name = getattr(state, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(state)
