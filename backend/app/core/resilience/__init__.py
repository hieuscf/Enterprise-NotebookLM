# =============================================================================
# File: __init__.py
# Module/Service: Core — Resilience
# Layer: Adapter
# Purpose: Reusable resilience primitives (circuit breakers) for outbound services.
# Responsibilities:
#   - Export circuit breaker abstractions independent of any LLM provider
# Dependencies:
#   - app.core.resilience.circuit_breaker, app.core.resilience.metrics
# Public Exports:
#   - CircuitBreakerConfig, CircuitBreakerOpenError, ResilientCircuitBreaker,
#     build_circuit_breaker, get_circuit_breaker_metrics
# Database/Table: N/A
# Related Modules: app.clients.llamaparse_client
# Important Notes: Each downstream service must use its own breaker instance.
# =============================================================================

from app.core.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    ResilientCircuitBreaker,
    build_circuit_breaker,
)
from app.core.resilience.metrics import get_circuit_breaker_metrics

__all__ = [
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "ResilientCircuitBreaker",
    "build_circuit_breaker",
    "get_circuit_breaker_metrics",
]
