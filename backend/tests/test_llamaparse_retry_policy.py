# =============================================================================
# File: test_llamaparse_retry_policy.py
# Module/Service: Pipeline Worker — HTTP Clients
# Layer: Adapter
# Purpose: Unit tests for reusable HTTP retry policy and LlamaParse mapping.
# Dependencies:
#   - pytest, tenacity
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.clients.retry_policy, app.clients.llamaparse_client
# Important Notes: No network calls.
# =============================================================================

from __future__ import annotations

import httpx
import pytest

from app.clients.llamaparse_client import (
    LlamaParseRequestError,
    LlamaParseServiceError,
    LlamaParseTimeoutError,
    is_retryable_llamaparse_error,
)
from app.clients.retry_policy import (
    NON_RETRYABLE_HTTP_STATUS_CODES,
    RETRYABLE_HTTP_STATUS_CODES,
    RetryPolicyConfig,
    call_with_retry,
    is_non_retryable_http_status,
    is_retryable_http_status,
)


def test_retryable_http_status_codes() -> None:
    assert is_retryable_http_status(500)
    assert is_retryable_http_status(502)
    assert is_retryable_http_status(503)
    assert is_retryable_http_status(504)
    assert not is_retryable_http_status(429)
    assert not is_retryable_http_status(501)


def test_non_retryable_http_status_codes() -> None:
    for status in NON_RETRYABLE_HTTP_STATUS_CODES:
        assert is_non_retryable_http_status(status)
        assert not is_retryable_http_status(status)


def test_llamaparse_error_mapping() -> None:
    assert is_retryable_llamaparse_error(LlamaParseTimeoutError("timeout"))
    assert is_retryable_llamaparse_error(
        LlamaParseServiceError("upstream", status_code=503),
    )
    assert is_retryable_llamaparse_error(
        LlamaParseServiceError("connection", status_code=None),
    )
    assert not is_retryable_llamaparse_error(
        LlamaParseRequestError("bad request", status_code=400),
    )
    assert not is_retryable_llamaparse_error(
        LlamaParseServiceError("rate limit", status_code=429),
    )


def test_call_with_retry_stops_after_max_attempts() -> None:
    config = RetryPolicyConfig(max_retries=2, min_wait_seconds=0, max_wait_seconds=0)
    calls = {"count": 0}

    def flaky() -> None:
        calls["count"] += 1
        raise LlamaParseServiceError("boom", status_code=500)

    with pytest.raises(LlamaParseServiceError, match="boom"):
        call_with_retry(
            config,
            flaky,
            is_retryable=is_retryable_llamaparse_error,
        )

    assert calls["count"] == 2


def test_call_with_retry_does_not_retry_request_errors() -> None:
    config = RetryPolicyConfig(max_retries=3, min_wait_seconds=0, max_wait_seconds=0)
    calls = {"count": 0}

    def bad_request() -> None:
        calls["count"] += 1
        raise LlamaParseRequestError("nope", status_code=401)

    with pytest.raises(LlamaParseRequestError):
        call_with_retry(
            config,
            bad_request,
            is_retryable=is_retryable_llamaparse_error,
        )

    assert calls["count"] == 1


def test_retry_policy_config_validation() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        RetryPolicyConfig(max_retries=0, min_wait_seconds=1, max_wait_seconds=2)
    with pytest.raises(ValueError, match="max_wait_seconds"):
        RetryPolicyConfig(max_retries=1, min_wait_seconds=5, max_wait_seconds=1)


def test_connect_error_is_retryable_via_service_error() -> None:
    exc = LlamaParseServiceError("connect", status_code=None)
    assert is_retryable_llamaparse_error(exc)

    transport = httpx.ConnectError("connection refused")
    assert isinstance(transport, httpx.ConnectError)
