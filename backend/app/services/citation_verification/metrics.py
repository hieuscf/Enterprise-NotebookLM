# =============================================================================
# File: metrics.py
# Module/Service: Citation Verification Layer (FR5) / Observability
# Layer: Adapter
# Purpose: In-process counters for citation verification (same pattern as FR14).
# Responsibilities:
#   - Track total / valid / invalid / latency / failure-reason counts
# Dependencies:
#   - threading (no new metrics framework)
# Public Exports:
#   - CitationVerificationMetrics, get_citation_verification_metrics,
#     reset_citation_verification_metrics_for_tests
# Database/Table: N/A
# Related Modules: citation_verification.service, app.core.fr14_metrics
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
#   - Project has no Prometheus exporter yet — in-process only.
# =============================================================================

from __future__ import annotations

import threading
from collections import defaultdict

METRIC_CITATION_VERIFICATION_TOTAL = "citation_verification_total"
METRIC_CITATION_VERIFICATION_VALID = "citation_verification_valid"
METRIC_CITATION_VERIFICATION_INVALID = "citation_verification_invalid"
METRIC_CITATION_VERIFICATION_LATENCY_MS_SUM = "citation_verification_latency_ms_sum"
METRIC_CITATION_VERIFICATION_FAILURE_REASON = "citation_verification_failure_reason"


class CitationVerificationMetrics:
    """Thread-safe FR5 counters (in-process until a metrics backend lands)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)

    def record_batch(
        self,
        *,
        total: int,
        valid: int,
        invalid: int,
        latency_ms: int,
        reasons: dict[str, int],
    ) -> None:
        with self._lock:
            self._counters[METRIC_CITATION_VERIFICATION_TOTAL] += float(max(0, total))
            self._counters[METRIC_CITATION_VERIFICATION_VALID] += float(max(0, valid))
            self._counters[METRIC_CITATION_VERIFICATION_INVALID] += float(max(0, invalid))
            self._counters[METRIC_CITATION_VERIFICATION_LATENCY_MS_SUM] += float(
                max(0, latency_ms)
            )
            for reason, count in reasons.items():
                self._counters[
                    f"{METRIC_CITATION_VERIFICATION_FAILURE_REASON}|reason={reason}"
                ] += float(max(0, count))

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._counters)


_metrics: CitationVerificationMetrics | None = None
_lock = threading.Lock()


def get_citation_verification_metrics() -> CitationVerificationMetrics:
    global _metrics
    with _lock:
        if _metrics is None:
            _metrics = CitationVerificationMetrics()
        return _metrics


def reset_citation_verification_metrics_for_tests() -> None:
    """Clear FR5 counters (tests only)."""
    global _metrics
    with _lock:
        _metrics = CitationVerificationMetrics()
