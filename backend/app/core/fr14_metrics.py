# =============================================================================
# File: fr14_metrics.py
# Module/Service: Observability Module (FR14)
# Layer: Adapter
# Purpose: In-process counters for Confidence Engine / Micro Agent observability.
# Responsibilities:
#   - Track agent triggers, latency, cost, confidence high/low totals
# Dependencies:
#   - threading (same pattern as circuit_breaker metrics)
# Public Exports:
#   - Fr14Metrics, get_fr14_metrics, reset_fr14_metrics_for_tests
# Database/Table: N/A
# Related Modules: ComplexQueryPipeline, System_Architecture Observability
# Important Notes:
#   - Project has OpenTelemetry tracing but no Prometheus exporter yet.
#   - TODO(prometheus): export these counters/histograms when a metrics backend
#     is added (agent_trigger_total, agent_latency_ms, agent_cost_usd,
#     confidence_distribution). Do NOT introduce a new metrics framework here.
# =============================================================================

from __future__ import annotations

import threading
from collections import defaultdict

# Stable metric name constants (do not hardcode strings at call sites).
METRIC_AGENT_TRIGGER_TOTAL = "agent_trigger_total"
METRIC_AGENT_LATENCY_MS_SUM = "agent_latency_ms_sum"
METRIC_AGENT_COST_USD_SUM = "agent_cost_usd_sum"
METRIC_CONFIDENCE_HIGH_TOTAL = "confidence_high_total"
METRIC_CONFIDENCE_LOW_TOTAL = "confidence_low_total"


class Fr14Metrics:
    """Thread-safe FR14 counters (in-process until Prometheus/OTLP metrics land)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)

    def record_confidence(self, *, level: str) -> None:
        key = (
            METRIC_CONFIDENCE_HIGH_TOTAL
            if level == "high"
            else METRIC_CONFIDENCE_LOW_TOTAL
        )
        with self._lock:
            self._counters[key] += 1

    def record_agent(
        self,
        *,
        agent_type: str,
        trigger_reason: str,
        latency_ms: int,
        cost_usd: float,
    ) -> None:
        with self._lock:
            self._counters[
                f"{METRIC_AGENT_TRIGGER_TOTAL}|agent_type={agent_type}|trigger_reason={trigger_reason}"
            ] += 1
            self._counters[f"{METRIC_AGENT_LATENCY_MS_SUM}|agent_type={agent_type}"] += float(
                max(0, latency_ms)
            )
            self._counters[f"{METRIC_AGENT_COST_USD_SUM}|agent_type={agent_type}"] += float(
                max(0.0, cost_usd)
            )

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._counters)


_metrics: Fr14Metrics | None = None
_lock = threading.Lock()


def get_fr14_metrics() -> Fr14Metrics:
    global _metrics
    with _lock:
        if _metrics is None:
            _metrics = Fr14Metrics()
        return _metrics


def reset_fr14_metrics_for_tests() -> None:
    """Clear FR14 counters (tests only)."""
    global _metrics
    with _lock:
        _metrics = Fr14Metrics()
