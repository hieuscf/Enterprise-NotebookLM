# =============================================================================
# File: llamaparse_client.py
# Module/Service: Pipeline Worker — Document Understanding ([AI])
# Layer: Adapter
# Purpose: LlamaParse REST client (upload → parse job → poll) for FR2 stage
#   `document_understanding`; returns Markdown + structured items tree.
# Responsibilities:
#   - POST /api/v1/beta/files → POST /api/v2/parse → GET /api/v2/parse/{id}
#   - Enforce a single wall-clock budget (LLAMAPARSE_TIMEOUT_SECONDS)
#   - Transient HTTP retry via app.clients.retry_policy (tenacity + jitter)
#   - Dedicated circuit breaker via app.core.resilience (pybreaker)
#   - Classify failures: request (4xx, permanent) vs service (retryable 5xx)
# Dependencies:
#   - httpx, tenacity, pybreaker, app.clients.retry_policy,
#     app.core.resilience, app.core.config.Settings
# Public Exports:
#   - LlamaParseClient, LlamaParseResult, get_llamaparse_client
#   - LlamaParseError, LlamaParseTimeoutError, LlamaParseRequestError,
#     LlamaParseServiceError, LlamaParseCircuitOpenError
#     get_llamaparse_circuit_breaker_metrics
# Database/Table: N/A (caller persists to document_versions)
# Related Modules: app.workers.stages.document_understanding, app.ai.layout
# Important Notes:
#   - This is NOT an LLM Provider call — never route Anthropic traffic here.
#   - Retries are bounded inside this client on purpose: a Celery-level retry
#     would re-upload and re-bill the document (see stage error mapping).
#   - `fast` tier cannot return markdown/items; keep tier >= cost_effective.
# =============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, TypeVar
from uuid import UUID

import httpx

from app.clients.retry_policy import (
    RetryContext,
    RetryPolicyConfig,
    call_with_retry,
    is_retryable_http_status,
)
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.resilience import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    ResilientCircuitBreaker,
    build_circuit_breaker,
    get_circuit_breaker_metrics,
)
from app.models.enums import FileType

LLAMAPARSE_CB_METRICS_PREFIX = "llamaparse_cb"
LLAMAPARSE_CB_OPEN_MESSAGE = "LlamaParse circuit breaker open"

logger = get_logger(__name__)

T = TypeVar("T")

FILES_ENDPOINT = "/api/v1/beta/files"
PARSE_ENDPOINT = "/api/v2/parse"

#: Result fields requested when polling; both require tier >= cost_effective.
RESULT_EXPAND = ("markdown_full", "items")

TERMINAL_SUCCESS = "COMPLETED"
TERMINAL_FAILURE = frozenset({"FAILED", "CANCELLED", "ERROR"})

CONTENT_TYPES: dict[FileType, str] = {
    FileType.pdf: "application/pdf",
    FileType.docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileType.xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileType.pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    FileType.txt: "text/plain",
}


class LlamaParseError(Exception):
    """Base error raised by the LlamaParse client."""


class LlamaParseTimeoutError(LlamaParseError):
    """Client polling / HTTP budget exhausted — not necessarily a remote job failure.

    Attributes:
        job_id: Remote parse job id when known (poll timeout path).
        remote_status: Last observed remote status (e.g. RUNNING) when known.
        client_timeout: True when our polling budget expired (vs transport timeout).
        budget_seconds: Configured client polling budget when applicable.
    """

    def __init__(
        self,
        message: str,
        *,
        job_id: str | None = None,
        remote_status: str | None = None,
        client_timeout: bool = False,
        budget_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.job_id = job_id
        self.remote_status = remote_status
        self.client_timeout = client_timeout
        self.budget_seconds = budget_seconds


class LlamaParseRequestError(LlamaParseError):
    """Permanent rejection: 4xx (bad key, unsupported file) or FAILED job.

    Retrying is pointless and would still be billed — callers must fail fast.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LlamaParseServiceError(LlamaParseError):
    """Retryable upstream failure: selected 5xx or transport error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LlamaParseCircuitOpenError(LlamaParseError):
    """Fail-fast when the dedicated LlamaParse circuit breaker is open."""

    def __init__(self, message: str = LLAMAPARSE_CB_OPEN_MESSAGE) -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class LlamaParseResult:
    """Successful parse of one document version.

    Attributes:
        job_id: LlamaParse job id (kept for support/audit trails).
        markdown: Full-document Markdown with heading structure preserved.
        pages: Structured items tree, one entry per page (may be empty when the
            configured tier does not return items).
        page_count: Number of pages LlamaParse reported.
        tier: Tier actually requested.
        attempts: How many top-level parse attempts were spent (>= 1).
        duration_ms: Wall-clock time across all attempts.
    """

    job_id: str
    markdown: str
    pages: list[dict[str, Any]]
    page_count: int
    tier: str
    attempts: int
    duration_ms: int


@dataclass
class _ParseSession:
    """Mutable counters for one ``parse`` invocation."""

    document_version_id: str | None = None
    request_id: str | None = None
    parse_attempts: int = 0


def is_retryable_llamaparse_error(exc: BaseException) -> bool:
    """Return True when an API call or poll-timeout may be retried."""
    if isinstance(exc, LlamaParseTimeoutError):
        return True
    if isinstance(exc, LlamaParseServiceError):
        if exc.status_code is None:
            return True
        return is_retryable_http_status(exc.status_code)
    return False


class LlamaParseClient:
    """Synchronous LlamaParse client sized for Celery worker usage."""

    def __init__(
        self,
        settings: Settings,
        *,
        circuit_breaker: ResilientCircuitBreaker | None = None,
    ) -> None:
        api_key = (settings.llamaparse_api_key or "").strip()
        if not api_key:
            raise LlamaParseRequestError("LLAMAPARSE_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = settings.llamaparse_base_url.rstrip("/")
        self._timeout_seconds = max(1, int(settings.llamaparse_timeout_seconds))
        self._tier = settings.llamaparse_tier
        self._poll_interval = max(0.1, float(settings.llamaparse_poll_interval_seconds))
        self._retry_policy = RetryPolicyConfig(
            max_retries=max(1, int(settings.llamaparse_max_retries)),
            min_wait_seconds=max(0.0, float(settings.llamaparse_retry_min_wait)),
            max_wait_seconds=max(
                float(settings.llamaparse_retry_min_wait),
                float(settings.llamaparse_retry_max_wait),
            ),
        )
        self._circuit_breaker = circuit_breaker or build_llamaparse_circuit_breaker(settings)
        self._session: _ParseSession | None = None

    # -- public API ---------------------------------------------------------

    def parse(
        self,
        *,
        data: bytes,
        filename: str,
        file_type: FileType,
        document_version_id: UUID | None = None,
        request_id: str | None = None,
    ) -> LlamaParseResult:
        """Parse one document, retrying bounded times on transient API failures.

        Args:
            data: Raw file bytes downloaded from object storage.
            filename: Original filename (LlamaParse uses the extension as a hint).
            file_type: Document file type, mapped to a MIME type.
            document_version_id: Optional pipeline id for retry observability logs.
            request_id: Optional correlation id for retry observability logs.

        Returns:
            Markdown + items tree for the document.

        Raises:
            LlamaParseRequestError: Permanent rejection — do not retry.
            LlamaParseServiceError: Upstream still failing after retry budget.
            LlamaParseTimeoutError: Budget exhausted after retries.
            LlamaParseCircuitOpenError: Circuit open — fail-fast without calling API.
        """
        started = time.perf_counter()
        content_type = CONTENT_TYPES.get(file_type, "application/octet-stream")
        self._session = _ParseSession(
            document_version_id=str(document_version_id) if document_version_id else None,
            request_id=request_id,
        )
        try:
            self._session.parse_attempts = 1

            def _protected_parse() -> tuple[str, str, list[dict[str, Any]], int]:
                return self._parse_once(
                    data=data,
                    filename=filename,
                    content_type=content_type,
                )

            job_id, markdown, pages, page_count = self._call_through_circuit_breaker(
                _protected_parse,
            )
        finally:
            session = self._session
            self._session = None

        assert session is not None
        return LlamaParseResult(
            job_id=job_id,
            markdown=markdown,
            pages=pages,
            page_count=page_count,
            tier=self._tier,
            attempts=session.parse_attempts,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    # -- one attempt --------------------------------------------------------

    def _parse_once(
        self,
        *,
        data: bytes,
        filename: str,
        content_type: str,
    ) -> tuple[str, str, list[dict[str, Any]], int]:
        deadline = time.monotonic() + self._timeout_seconds
        with self._http_client() as client:
            file_id = self._upload_file(
                client,
                data=data,
                filename=filename,
                content_type=content_type,
            )
            job_id = self._create_job(client, file_id=file_id)
            logger.info(
                "llamaparse_job_submitted",
                job_id=job_id,
                document_version_id=(
                    self._session.document_version_id if self._session else None
                ),
                budget_seconds=self._timeout_seconds,
            )
            payload = self._poll_job(client, job_id=job_id, deadline=deadline)

        markdown = _extract_markdown(payload)
        if not markdown.strip():
            raise LlamaParseRequestError(
                f"LlamaParse job {job_id} returned no Markdown content "
                "(scanned document without text, or tier does not support markdown)"
            )
        pages = _extract_item_pages(payload)
        return job_id, markdown, pages, _extract_page_count(payload, pages)

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout_seconds),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
        )

    def _upload_file(
        self,
        client: httpx.Client,
        *,
        data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        response = self._send(
            client,
            "POST",
            FILES_ENDPOINT,
            context="file upload",
            files={"file": (filename, data, content_type)},
            data={"purpose": "parse"},
        )
        payload = _json_object(response, context="file upload")
        file_id = payload.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise LlamaParseServiceError("File upload response is missing an 'id'")
        return file_id

    def _create_job(self, client: httpx.Client, *, file_id: str) -> str:
        response = self._send(
            client,
            "POST",
            PARSE_ENDPOINT,
            context="parse job creation",
            json={"file_id": file_id, "tier": self._tier, "version": "latest"},
        )
        payload = _json_object(response, context="parse job creation")
        job_id = payload.get("id") or (payload.get("job") or {}).get("id")
        if not isinstance(job_id, str) or not job_id:
            raise LlamaParseServiceError("Parse job response is missing an 'id'")
        return job_id

    def _poll_job(
        self,
        client: httpx.Client,
        *,
        job_id: str,
        deadline: float,
    ) -> dict[str, Any]:
        params = [("expand", value) for value in RESULT_EXPAND]
        while True:
            response = self._send(
                client,
                "GET",
                f"{PARSE_ENDPOINT}/{job_id}",
                context=f"parse job {job_id} polling",
                params=params,
            )
            _capture_request_id(self._session, response)
            payload = _json_object(response, context=f"parse job {job_id} polling")
            status = _extract_status(payload)
            if status == TERMINAL_SUCCESS:
                return payload
            if status in TERMINAL_FAILURE:
                raise LlamaParseRequestError(
                    f"LlamaParse job {job_id} ended as {status}: {_extract_job_error(payload)}"
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning(
                    "llamaparse_poll_timeout",
                    job_id=job_id,
                    attempt=self._session.parse_attempts if self._session else 1,
                    budget_seconds=self._timeout_seconds,
                    remote_status=status,
                    client_timeout=True,
                )
                # Best-effort cancel to avoid continued remote billing; never invent
                # endpoints — POST /api/v2/parse/{id}/cancel is the documented API.
                self._best_effort_cancel(client, job_id=job_id)
                raise LlamaParseTimeoutError(
                    f"LlamaParse client polling budget expired while remote job "
                    f"{job_id} was still {status}.",
                    job_id=job_id,
                    remote_status=status,
                    client_timeout=True,
                    budget_seconds=self._timeout_seconds,
                )
            time.sleep(min(self._poll_interval, remaining))

    def _best_effort_cancel(self, client: httpx.Client, *, job_id: str) -> None:
        """Cancel a still-RUNNING remote job after client budget expiry (best effort)."""
        try:
            response = client.request(
                "POST",
                f"{PARSE_ENDPOINT}/{job_id}/cancel",
            )
            if response.status_code < 400:
                logger.info("llamaparse_job_cancel_requested", job_id=job_id)
                return
            logger.warning(
                "llamaparse_job_cancel_failed",
                job_id=job_id,
                status_code=response.status_code,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "llamaparse_job_cancel_failed",
                job_id=job_id,
                error=str(exc),
            )

    def _send(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        *,
        context: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Perform one HTTP request with transient retry on selected failures."""

        def _request_once() -> httpx.Response:
            try:
                response = client.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                raise LlamaParseTimeoutError(f"LlamaParse {context} timed out: {exc}") from exc
            except httpx.ConnectError as exc:
                raise LlamaParseServiceError(
                    f"LlamaParse {context} connection error: {exc}",
                    status_code=None,
                ) from exc
            except httpx.HTTPError as exc:
                raise LlamaParseRequestError(f"LlamaParse {context} transport error: {exc}") from exc

            _raise_for_status(response, context=context)
            _capture_request_id(self._session, response)
            return response

        return call_with_retry(
            self._retry_policy,
            _request_once,
            is_retryable=is_retryable_llamaparse_error,
            context=self._retry_context(),
        )

    def _call_through_circuit_breaker(self, func: Callable[[], T]) -> T:
        """Execute ``func`` behind the LlamaParse circuit breaker."""
        try:
            return self._circuit_breaker.call(func)
        except CircuitBreakerOpenError as exc:
            raise LlamaParseCircuitOpenError(LLAMAPARSE_CB_OPEN_MESSAGE) from exc

    def _retry_context(self) -> RetryContext:
        session = self._session
        return RetryContext(
            document_version_id=session.document_version_id if session else None,
            request_id=session.request_id if session else None,
            client_name="llamaparse",
        )


def _raise_for_status(response: httpx.Response, *, context: str) -> None:
    status = response.status_code
    if status < 400:
        return
    detail = _error_detail(response)
    message = f"LlamaParse {context} failed: HTTP {status} — {detail}"
    if status == 408:
        raise LlamaParseTimeoutError(message)
    if is_retryable_http_status(status):
        raise LlamaParseServiceError(message, status_code=status)
    raise LlamaParseRequestError(message, status_code=status)


def _capture_request_id(session: _ParseSession | None, response: httpx.Response) -> None:
    if session is None or session.request_id:
        return
    for header in ("x-request-id", "request-id", "x-correlation-id"):
        value = response.headers.get(header)
        if value:
            session.request_id = value
            return


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "")[:500]
    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            value = payload.get(key)
            if value:
                return str(value)[:500]
    return str(payload)[:500]


def _json_object(response: httpx.Response, *, context: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise LlamaParseServiceError(f"LlamaParse {context} returned a non-JSON body") from exc
    if not isinstance(payload, dict):
        raise LlamaParseServiceError(f"LlamaParse {context} returned a non-object body")
    return payload


def _extract_status(payload: dict[str, Any]) -> str:
    job = payload.get("job")
    status = (job or {}).get("status") if isinstance(job, dict) else None
    status = status or payload.get("status")
    return str(status or "PENDING").upper()


def _extract_job_error(payload: dict[str, Any]) -> str:
    job = payload.get("job") if isinstance(payload.get("job"), dict) else {}
    for source in (job, payload):
        for key in ("error_message", "error_code", "error", "detail"):
            value = source.get(key)
            if value:
                return str(value)[:500]
    return "no error message returned"


def _extract_markdown(payload: dict[str, Any]) -> str:
    """Prefer `markdown_full`; fall back to joining per-page markdown."""
    full = payload.get("markdown_full")
    if isinstance(full, str) and full.strip():
        return full
    if isinstance(full, dict):
        nested = full.get("markdown")
        if isinstance(nested, str) and nested.strip():
            return nested

    markdown = payload.get("markdown")
    if isinstance(markdown, str):
        return markdown
    if isinstance(markdown, dict):
        pages = markdown.get("pages")
        if isinstance(pages, list):
            parts = [str(page.get("markdown") or "") for page in pages if isinstance(page, dict)]
            return "\n\n".join(part for part in parts if part.strip())
    return ""


def _extract_item_pages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if isinstance(items, dict):
        pages = items.get("pages")
    elif isinstance(items, list):
        pages = items
    else:
        pages = None
    if not isinstance(pages, list):
        return []
    return [page for page in pages if isinstance(page, dict)]


def _extract_page_count(payload: dict[str, Any], pages: list[dict[str, Any]]) -> int:
    for source in (payload.get("job"), payload.get("job_metadata"), payload):
        if not isinstance(source, dict):
            continue
        for key in ("page_count", "pages_parsed", "num_pages"):
            value = source.get(key)
            if isinstance(value, int) and value > 0:
                return value
    return len(pages)


def build_llamaparse_circuit_breaker(settings: Settings) -> ResilientCircuitBreaker:
    """Build the dedicated LlamaParse circuit breaker (never shared with LLM providers)."""
    return build_circuit_breaker(
        CircuitBreakerConfig(
            name="llamaparse",
            failure_threshold=max(1, int(settings.llamaparse_cb_failure_threshold)),
            reset_timeout_seconds=max(1, int(settings.llamaparse_cb_reset_timeout)),
            success_threshold=max(1, int(settings.llamaparse_cb_success_threshold)),
            metrics_prefix=LLAMAPARSE_CB_METRICS_PREFIX,
        ),
        exclude=(LlamaParseRequestError, LlamaParseCircuitOpenError),
    )


def get_llamaparse_circuit_breaker_metrics() -> dict[str, int]:
    """Return in-process LlamaParse circuit breaker counters."""
    return get_circuit_breaker_metrics(LLAMAPARSE_CB_METRICS_PREFIX).snapshot()


@lru_cache
def get_llamaparse_client() -> LlamaParseClient:
    return LlamaParseClient(get_settings())
