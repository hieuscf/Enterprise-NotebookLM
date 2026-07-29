# =============================================================================
# File: retry_policy.py
# Module/Service: Pipeline Worker — HTTP Clients
# Layer: Adapter
# Purpose: Reusable tenacity-based retry for transient HTTP / transport failures.
# Responsibilities:
#   - Exponential backoff with jitter driven by Settings / ENV
#   - Structured retry logging (attempt, exception, wait_time, optional context)
# Dependencies:
#   - tenacity, app.core.logging
# Public Exports:
#   - RetryPolicyConfig, RetryContext, is_retryable_http_status,
#     build_retrying, retry_transient, call_with_retry
# Database/Table: N/A
# Related Modules: app.clients.llamaparse_client
# Important Notes: Parser-specific exception mapping stays in each client.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.logging import get_logger

P = ParamSpec("P")
T = TypeVar("T")

logger = get_logger(__name__)

RETRYABLE_HTTP_STATUS_CODES: frozenset[int] = frozenset({500, 502, 503, 504})
NON_RETRYABLE_HTTP_STATUS_CODES: frozenset[int] = frozenset({400, 401, 403, 404, 409, 422})


@dataclass(frozen=True, slots=True)
class RetryPolicyConfig:
    """Configurable retry budget for outbound HTTP clients."""

    max_retries: int
    min_wait_seconds: float
    max_wait_seconds: float

    def __post_init__(self) -> None:
        if self.max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        if self.min_wait_seconds < 0:
            raise ValueError("min_wait_seconds must be >= 0")
        if self.max_wait_seconds < self.min_wait_seconds:
            raise ValueError("max_wait_seconds must be >= min_wait_seconds")


@dataclass(frozen=True, slots=True)
class RetryContext:
    """Optional observability fields attached to retry log lines."""

    document_version_id: str | None = None
    request_id: str | None = None
    client_name: str | None = None


def is_retryable_http_status(status_code: int) -> bool:
    """Return True only for explicitly retryable HTTP status codes."""
    return status_code in RETRYABLE_HTTP_STATUS_CODES


def is_non_retryable_http_status(status_code: int) -> bool:
    """Return True for client/request errors that must fail immediately."""
    return status_code in NON_RETRYABLE_HTTP_STATUS_CODES


def build_retrying(
    config: RetryPolicyConfig,
    *,
    is_retryable: Callable[[BaseException], bool],
    context: RetryContext | None = None,
) -> Retrying:
    """Build a ``tenacity.Retrying`` executor from policy + predicate."""
    return Retrying(
        stop=stop_after_attempt(config.max_retries),
        wait=wait_exponential_jitter(
            initial=config.min_wait_seconds,
            max=config.max_wait_seconds,
        ),
        retry=retry_if_exception(is_retryable),
        reraise=True,
        before_sleep=_build_before_sleep(context),
    )


def retry_transient(
    config: RetryPolicyConfig,
    *,
    is_retryable: Callable[[BaseException], bool],
    context: RetryContext | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator factory for transient HTTP retry with structured logging."""

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        retrying = build_retrying(config, is_retryable=is_retryable, context=context)

        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in retrying:
                with attempt:
                    return func(*args, **kwargs)
            raise RuntimeError("retry_transient exhausted without result")  # pragma: no cover

        return wrapper

    return decorator


def call_with_retry(
    config: RetryPolicyConfig,
    func: Callable[[], T],
    *,
    is_retryable: Callable[[BaseException], bool],
    context: RetryContext | None = None,
) -> T:
    """Invoke ``func`` with the configured retry policy (non-decorator form)."""
    retrying = build_retrying(config, is_retryable=is_retryable, context=context)
    for attempt in retrying:
        with attempt:
            return func()
    raise RuntimeError("call_with_retry exhausted without result")  # pragma: no cover


def _build_before_sleep(
    context: RetryContext | None,
) -> Callable[[RetryCallState], None]:
    def _before_sleep(retry_state: RetryCallState) -> None:
        outcome = retry_state.outcome
        exception = outcome.exception() if outcome is not None else None
        wait_time = retry_state.next_action.sleep if retry_state.next_action else None
        fields: dict[str, Any] = {
            "retry_attempt": retry_state.attempt_number,
            "exception": str(exception) if exception is not None else None,
            "wait_time": wait_time,
        }
        if context is not None:
            if context.document_version_id is not None:
                fields["document_version_id"] = context.document_version_id
            if context.request_id is not None:
                fields["request_id"] = context.request_id
            if context.client_name is not None:
                fields["client_name"] = context.client_name
        logger.warning("http_client_retry", **fields)

    return _before_sleep
