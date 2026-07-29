# =============================================================================
# File: llamaparse.py
# Module/Service: Pipeline Worker — Document Understanding ([AI])
# Layer: Adapter
# Purpose: LlamaParse REST client (upload → parse job → poll) for FR2 stage
#   `document_understanding`; returns Markdown + structured items tree.
# Responsibilities:
#   - POST /api/v1/beta/files → POST /api/v2/parse → GET /api/v2/parse/{id}
#   - Enforce a single wall-clock budget (LLAMAPARSE_TIMEOUT_SECONDS)
#   - Bounded retry with exponential backoff on timeout / 429 / 5xx
#   - Classify failures: request (4xx, permanent) vs service (retryable)
# Dependencies:
#   - httpx, app.core.config.Settings, app.models.enums.FileType
# Public Exports:
#   - LlamaParseClient, LlamaParseResult, get_llamaparse_client
#   - LlamaParseError, LlamaParseTimeoutError, LlamaParseRequestError,
#     LlamaParseServiceError
# Database/Table: N/A (caller persists to document_versions)
# Related Modules: app.workers.stages.document_understanding, app.ai.layout
# Important Notes:
#   - This is NOT an LLM Provider call — never route Anthropic traffic here.
#   - Retries are bounded inside this adapter on purpose: a Celery-level retry
#     would re-upload and re-bill the document (see stage error mapping).
#   - `fast` tier cannot return markdown/items; keep tier >= cost_effective.
# =============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.models.enums import FileType

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
    """Base error raised by the LlamaParse adapter."""


class LlamaParseTimeoutError(LlamaParseError):
    """Wall-clock budget exhausted, or a single HTTP call timed out."""


class LlamaParseRequestError(LlamaParseError):
    """Permanent rejection: 4xx (bad key, unsupported file) or FAILED job.

    Retrying is pointless and would still be billed — callers must fail fast.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LlamaParseServiceError(LlamaParseError):
    """Retryable upstream failure: 429, 5xx, or transport error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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
        attempts: How many parse attempts were spent (>= 1).
        duration_ms: Wall-clock time across all attempts.
    """

    job_id: str
    markdown: str
    pages: list[dict[str, Any]]
    page_count: int
    tier: str
    attempts: int
    duration_ms: int


class LlamaParseClient:
    """Synchronous LlamaParse client sized for Celery worker usage."""

    def __init__(self, settings: Settings) -> None:
        api_key = (settings.llamaparse_api_key or "").strip()
        if not api_key:
            raise LlamaParseRequestError("LLAMAPARSE_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = settings.llamaparse_base_url.rstrip("/")
        self._timeout_seconds = max(1, int(settings.llamaparse_timeout_seconds))
        self._max_retries = max(1, int(settings.llamaparse_max_retries))
        self._tier = settings.llamaparse_tier
        self._poll_interval = max(0.1, float(settings.llamaparse_poll_interval_seconds))

    # -- public API ---------------------------------------------------------

    def parse(
        self,
        *,
        data: bytes,
        filename: str,
        file_type: FileType,
    ) -> LlamaParseResult:
        """Parse one document, retrying bounded times on transient failures.

        Args:
            data: Raw file bytes downloaded from object storage.
            filename: Original filename (LlamaParse uses the extension as a hint).
            file_type: Document file type, mapped to a MIME type.

        Returns:
            Markdown + items tree for the document.

        Raises:
            LlamaParseRequestError: Permanent rejection — do not retry.
            LlamaParseServiceError: Upstream still failing after ``max_retries``.
            LlamaParseTimeoutError: Budget exhausted on every attempt.
        """
        started = time.perf_counter()
        content_type = CONTENT_TYPES.get(file_type, "application/octet-stream")
        last_error: LlamaParseError | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                job_id, markdown, pages, page_count = self._parse_once(
                    data=data,
                    filename=filename,
                    content_type=content_type,
                )
            except (LlamaParseTimeoutError, LlamaParseServiceError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                time.sleep(self._backoff_seconds(attempt))
                continue

            return LlamaParseResult(
                job_id=job_id,
                markdown=markdown,
                pages=pages,
                page_count=page_count,
                tier=self._tier,
                attempts=attempt,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        assert last_error is not None  # loop only exits early via return
        raise last_error

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
                raise LlamaParseTimeoutError(
                    f"LlamaParse job {job_id} still {status} after "
                    f"{self._timeout_seconds}s budget"
                )
            time.sleep(min(self._poll_interval, remaining))

    def _send(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        *,
        context: str,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise LlamaParseTimeoutError(f"LlamaParse {context} timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LlamaParseServiceError(f"LlamaParse {context} transport error: {exc}") from exc

        _raise_for_status(response, context=context)
        return response

    def _backoff_seconds(self, attempt: int) -> float:
        """Exponential backoff capped so it cannot outlive the stage budget."""
        return float(min(2 ** (attempt - 1), max(1, self._timeout_seconds // 4)))


def _raise_for_status(response: httpx.Response, *, context: str) -> None:
    status = response.status_code
    if status < 400:
        return
    detail = _error_detail(response)
    message = f"LlamaParse {context} failed: HTTP {status} — {detail}"
    if status == 408:
        raise LlamaParseTimeoutError(message)
    if status == 429 or status >= 500:
        raise LlamaParseServiceError(message, status_code=status)
    raise LlamaParseRequestError(message, status_code=status)


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


@lru_cache
def get_llamaparse_client() -> LlamaParseClient:
    return LlamaParseClient(get_settings())
