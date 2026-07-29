# =============================================================================
# File: metrics.py
# Module/Service: Core — Resilience
# Layer: Adapter
# Purpose: In-process counters for circuit breaker observability per service.
# Responsibilities:
#   - Track open/close/half-open/trip/fail-fast totals with isolated namespaces
# Dependencies:
#   - threading
# Public Exports:
#   - CircuitBreakerMetrics, get_circuit_breaker_metrics
# Database/Table: N/A
# Related Modules: app.core.resilience.circuit_breaker
# Important Notes: Prefix isolates LlamaParse metrics from LLM provider metrics.
# =============================================================================

from __future__ import annotations

import threading
from collections import defaultdict


class CircuitBreakerMetrics:
    """Thread-safe counter registry for one circuit breaker namespace."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix.rstrip("_")
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)

    def inc_open(self) -> None:
        self._increment("open_total")

    def inc_half_open(self) -> None:
        self._increment("half_open_total")

    def inc_close(self) -> None:
        self._increment("close_total")

    def inc_trip(self) -> None:
        self._increment("trip_total")

    def inc_fail_fast(self) -> None:
        self._increment("fail_fast_total")

    def snapshot(self) -> dict[str, int]:
        """Return a copy of all counters for this namespace."""
        with self._lock:
            return {f"{self._prefix}_{key}": value for key, value in self._counters.items()}

    def _increment(self, suffix: str) -> None:
        with self._lock:
            self._counters[suffix] += 1


_metrics_registry: dict[str, CircuitBreakerMetrics] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker_metrics(prefix: str) -> CircuitBreakerMetrics:
    """Return (or create) the metrics registry for ``prefix``."""
    normalized = prefix.rstrip("_")
    with _registry_lock:
        existing = _metrics_registry.get(normalized)
        if existing is not None:
            return existing
        metrics = CircuitBreakerMetrics(normalized)
        _metrics_registry[normalized] = metrics
        return metrics


def reset_circuit_breaker_metrics_for_tests() -> None:
    """Clear all in-process circuit breaker counters (tests only)."""
    with _registry_lock:
        _metrics_registry.clear()
