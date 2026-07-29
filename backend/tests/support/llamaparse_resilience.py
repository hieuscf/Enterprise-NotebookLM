# =============================================================================
# File: llamaparse_resilience.py
# Module/Service: Pipeline Worker — LlamaParse Client
# Layer: Adapter
# Purpose: Shared stubs and helpers for LlamaParse retry/circuit breaker tests.
# Dependencies:
#   - httpx, app.clients.llamaparse_client, app.core.config
# Public Exports:
#   - llamaparse_test_settings, StubLlamaParseClient, success_handler
# Database/Table: N/A
# Related Modules: tests.test_llamaparse_resilience
# Important Notes: No live network calls.
# =============================================================================

from __future__ import annotations

from typing import Any

import httpx

from app.clients.llamaparse_client import LlamaParseClient, build_llamaparse_circuit_breaker
from app.core.config import Settings
from app.core.resilience import CircuitBreakerConfig, ResilientCircuitBreaker, build_circuit_breaker


def llamaparse_test_settings(**overrides: object) -> Settings:
    """Build Settings for resilience tests with fast retry/cooldown defaults."""
    base: dict[str, object] = {
        "llamaparse_api_key": "test-key",
        "llamaparse_max_retries": 3,
        "llamaparse_retry_min_wait": 0,
        "llamaparse_retry_max_wait": 0,
        "llamaparse_cb_failure_threshold": 5,
        "llamaparse_cb_reset_timeout": 60,
        "llamaparse_cb_success_threshold": 1,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


class StubLlamaParseClient(LlamaParseClient):
    """LlamaParseClient wired to httpx MockTransport (no network)."""

    def __init__(
        self,
        settings: Settings,
        handler: httpx.MockTransport | Any,
        *,
        circuit_breaker: ResilientCircuitBreaker | None = None,
    ) -> None:
        breaker = circuit_breaker or build_llamaparse_circuit_breaker(settings)
        super().__init__(settings, circuit_breaker=breaker)
        self._handler = handler

    def _http_client(self) -> httpx.Client:
        transport = (
            self._handler
            if isinstance(self._handler, httpx.MockTransport)
            else httpx.MockTransport(self._handler)
        )
        return httpx.Client(
            transport=transport,
            base_url="https://parse.test",
            headers={"Accept": "application/json"},
        )


def success_handler() -> httpx.MockTransport:
    """Return a transport that completes a parse job on the first attempt."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file-1"})
        if path == "/api/v2/parse":
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(
            200,
            json={
                "job": {"id": "job-1", "status": "COMPLETED"},
                "markdown_full": "# OK",
            },
        )

    return httpx.MockTransport(handler)


def build_other_service_breaker(prefix: str) -> ResilientCircuitBreaker:
    """Build a non-LlamaParse breaker to verify namespace isolation in tests."""
    return build_circuit_breaker(
        CircuitBreakerConfig(
            name=f"other-{prefix}",
            failure_threshold=2,
            reset_timeout_seconds=60,
            success_threshold=1,
            metrics_prefix=prefix,
        ),
    )
