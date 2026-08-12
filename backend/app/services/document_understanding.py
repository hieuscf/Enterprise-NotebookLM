# =============================================================================
# File: document_understanding.py
# Module/Service: Document Ingestion Service — Document Understanding
# Layer: Service
# Purpose: Business logic for v3 Document Understanding — parse source files into
#   Markdown + Layout Analysis + Metadata Extraction (FR2, UC2, TASKS 1.4).
# Responsibilities:
#   - Validate inputs before invoking a parser
#   - Download source bytes, parse, build layout, extract metadata
#   - Persist Markdown / layout / interim segments artifacts with rollback
#   - Support idempotent skip when durable outputs already exist
#   - Configurable LlamaParse → local-OCR fallback on client poll timeout / 5xx
# Dependencies:
#   - app.adapters.llamaparse, app.adapters.minio_storage, app.ai.layout,
#     app.ai.ocr (local parser), app.workers.artifacts, app.core.config
# Public Exports:
#   - DocumentUnderstandingService, DocumentUnderstandingResult
#   - DocumentParser, LlamaParseDocumentParser, LocalOcrDocumentParser
#   - PARSER_LLAMAPARSE, PARSER_LOCAL_OCR, SUPPORTED_FILE_TYPES
#   - build_document_understanding_service, should_fallback_to_local_ocr
# Database/Table: document_versions (parser, markdown_storage_path, layout_metadata)
# Related Modules: app.workers.stages.document_understanding
# Important Notes:
#   - NO LLM Provider (Anthropic) call here — parsers are external API or local OCR.
#   - Parser selection is explicit via Settings.document_parser.
#   - LlamaParse poll-budget expiry is a client_timeout, not a remote job failure.
#   - Auth / quota / unsupported-file errors never fall back to local OCR.
# =============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from minio.error import S3Error

from app.adapters.llamaparse import (
    LlamaParseCircuitOpenError,
    LlamaParseClient,
    LlamaParseError,
    LlamaParseRequestError,
    LlamaParseServiceError,
    LlamaParseTimeoutError,
)
from app.adapters.minio_storage import MinioStorageAdapter
from app.ai.layout import (
    PAGINATED_FILE_TYPES,
    LayoutAnalysis,
    MarkdownMetrics,
    build_layout_analysis,
    build_layout_artifact,
    build_layout_metadata,
    extract_markdown_metrics,
    resolve_page_count,
)
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.documents import Document, DocumentVersion
from app.models.enums import FileType
from app.workers.artifacts import (
    LAYOUT_ARTIFACT,
    MARKDOWN_ARTIFACT,
    pipeline_artifact_key,
    save_json_artifact,
    save_text_output,
)
from app.workers.pipeline_errors import DataPipelineError, TransientPipelineError

logger = get_logger(__name__)

PARSER_LLAMAPARSE = "llamaparse"
PARSER_LOCAL_OCR = "local-ocr"
SUPPORTED_FILE_TYPES = frozenset(FileType)

#: Workspace-facing message when Document Understanding fails terminally.
USER_PARSE_FAILED = "Không thể xử lý tài liệu. Vui lòng thử lại."

#: HTTP statuses that must never be hidden behind local OCR fallback.
_NO_FALLBACK_STATUS_CODES = frozenset({401, 402, 403, 429})


@dataclass(frozen=True, slots=True)
class ParseOutput:
    """Parser-agnostic output feeding Layout Analysis."""

    markdown: str
    item_pages: list[dict[str, Any]]
    reported_page_count: int
    job_id: str | None = None
    tier: str | None = None
    attempts: int = 1
    parse_duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class DocumentUnderstandingResult:
    """Service output consumed by the Celery stage for DB persistence."""

    parser: str
    markdown_storage_path: str
    layout_metadata: dict[str, Any]
    stage_metadata: dict[str, Any]
    artifact_keys: tuple[str, ...]


class DocumentParser(Protocol):
    """Pluggable document parser (LlamaParse REST API or local OCR)."""

    parser_name: str

    def parse(
        self,
        *,
        data: bytes,
        storage_path: str,
        file_type: FileType,
    ) -> ParseOutput: ...


class LlamaParseDocumentParser:
    """LlamaParse adapter implementing ``DocumentParser``.

    Raises ``LlamaParseError`` subclasses so the service can apply fallback policy.
    """

    parser_name = PARSER_LLAMAPARSE

    def __init__(self, client: LlamaParseClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    def parse(
        self,
        *,
        data: bytes,
        storage_path: str,
        file_type: FileType,
    ) -> ParseOutput:
        filename = storage_path.rsplit("/", 1)[-1] or f"document.{file_type.value}"
        logger.info(
            "Calling LlamaParse",
            filename=filename,
            file_type=file_type.value,
            tier=self._settings.llamaparse_tier,
            timeout_seconds=self._settings.llamaparse_timeout_seconds,
            max_retries=self._settings.llamaparse_max_retries,
        )
        result = self._client.parse(data=data, filename=filename, file_type=file_type)
        logger.info(
            "LlamaParse finished",
            job_id=result.job_id,
            attempts=result.attempts,
            parse_duration_ms=result.duration_ms,
            page_count=result.page_count,
        )
        return ParseOutput(
            markdown=result.markdown,
            item_pages=result.pages,
            reported_page_count=result.page_count,
            job_id=result.job_id,
            tier=result.tier,
            attempts=result.attempts,
            parse_duration_ms=result.duration_ms,
        )


class LocalOcrDocumentParser:
    """Offline / fallback parser producing LlamaParse-shaped item_pages."""

    parser_name = PARSER_LOCAL_OCR

    def parse(
        self,
        *,
        data: bytes,
        storage_path: str,
        file_type: FileType,
    ) -> ParseOutput:
        from app.ai.ocr import EmptyOcrError, run_ocr_cleaning

        started = time.perf_counter()
        try:
            result = run_ocr_cleaning(file_type=file_type, data=data)
        except EmptyOcrError as exc:
            raise DataPipelineError(
                str(exc),
                user_message=USER_PARSE_FAILED,
            ) from exc
        except (ValueError, OSError) as exc:
            raise DataPipelineError(
                f"Local parse failed for {file_type.value}: {exc}",
                user_message=USER_PARSE_FAILED,
            ) from exc
        except Exception as exc:
            raise DataPipelineError(
                f"Local parse error ({file_type.value}): {exc}",
                user_message=USER_PARSE_FAILED,
            ) from exc

        item_pages = _segments_to_item_pages(result.segments)
        return ParseOutput(
            markdown=_markdown_from_item_pages(item_pages),
            item_pages=item_pages,
            reported_page_count=result.page_count if file_type in PAGINATED_FILE_TYPES else 0,
            parse_duration_ms=int((time.perf_counter() - started) * 1000),
        )


class DocumentUnderstandingService:
    """Parse one document version into Markdown, layout artifacts and metadata."""

    def __init__(
        self,
        *,
        storage: MinioStorageAdapter,
        settings: Settings,
        parser: DocumentParser,
        fallback_parser: DocumentParser | None = None,
    ) -> None:
        self._storage = storage
        self._settings = settings
        self._parser = parser
        self._fallback_parser = fallback_parser

    def execute(
        self,
        *,
        document_version_id: UUID,
        version: DocumentVersion,
        document: Document,
        force_reparse: bool = False,
    ) -> DocumentUnderstandingResult:
        """Run Document Understanding for one version (no DB writes).

        Args:
            document_version_id: Target ``document_versions.id``.
            version: Loaded ORM row (validated by caller).
            document: Parent document row (validated by caller).
            force_reparse: When False, skip parsing if durable outputs exist.

        Returns:
            Parsed outputs and stage metadata for the Celery stage to persist.

        Raises:
            DataPipelineError: Validation, parse, or empty-content failures.
            TransientPipelineError: Temporary MinIO read/write failures.
        """
        started = time.perf_counter()
        self._validate_inputs(version=version, document=document)

        if not force_reparse and self._should_skip_reparse(version):
            logger.info(
                "Skipping document understanding reparse",
                document_version_id=str(document_version_id),
                markdown_storage_path=version.markdown_storage_path,
            )
            return self._result_from_existing(
                document_version_id=document_version_id,
                version=version,
                document=document,
                started=started,
            )

        logger.info(
            "document_understanding_started",
            document_version_id=str(document_version_id),
            parser=self._parser.parser_name,
            file_type=document.file_type.value,
            storage_path=version.storage_path,
        )

        raw = self._download_bytes(version.storage_path)
        logger.info(
            "Downloaded source",
            document_version_id=str(document_version_id),
            byte_length=len(raw),
        )

        output, parse_meta = self._parse_with_policy(
            data=raw,
            storage_path=version.storage_path,
            file_type=document.file_type,
            document_version_id=document_version_id,
        )

        metrics = extract_markdown_metrics(output.markdown)
        analysis = build_layout_analysis(
            markdown=output.markdown,
            item_pages=output.item_pages,
            reported_page_count=output.reported_page_count,
        )
        if not analysis.blocks:
            raise DataPipelineError(
                "Document Understanding produced no layout blocks — "
                "the parsed Markdown has no usable content",
                user_message=USER_PARSE_FAILED,
                diagnostics=parse_meta,
            )

        parser = parse_meta["actual_parser"]
        keys = self._persist_outputs(
            document_version_id=document_version_id,
            storage_path=version.storage_path,
            parser=parser,
            markdown=output.markdown,
            analysis=analysis,
            metrics=metrics,
            job_id=output.job_id,
        )

        layout_metadata = build_layout_metadata(
            analysis=analysis,
            metrics=metrics,
            parser=parser,
            tier=output.tier,
            job_id=output.job_id,
            layout_artifact_key=keys["layout_artifact_key"],
        )
        page_count = resolve_page_count(analysis=analysis, file_type=document.file_type)

        stage_metadata = {
            "document_version_id": str(document_version_id),
            "file_type": document.file_type.value,
            "parser": parser,
            "requested_parser": parse_meta["requested_parser"],
            "actual_parser": parser,
            "fallback": parse_meta["fallback"],
            "fallback_reason": parse_meta.get("fallback_reason"),
            "layout_source": analysis.source,
            "llamaparse_job_id": parse_meta.get("llamaparse_job_id") or output.job_id,
            "llamaparse_tier": output.tier,
            "llamaparse_attempts": parse_meta.get("llamaparse_attempts"),
            "llamaparse_timeout_seconds": parse_meta.get("llamaparse_timeout_seconds"),
            "client_timeout": parse_meta.get("client_timeout"),
            "remote_status": parse_meta.get("remote_status"),
            "parse_duration_ms": output.parse_duration_ms,
            "page_count": page_count,
            "section_count": analysis.section_count,
            "block_count": len(analysis.blocks),
            "markdown_bytes": len(output.markdown.encode("utf-8")),
            **metrics.as_dict(),
            "markdown_storage_path": keys["markdown_storage_path"],
            "layout_artifact_key": keys["layout_artifact_key"],
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

        artifact_keys = (
            keys["markdown_storage_path"],
            keys["layout_artifact_key"],
        )

        logger.info(
            "Document understanding completed",
            document_version_id=str(document_version_id),
            parser=parser,
            block_count=len(analysis.blocks),
            duration_ms=stage_metadata["duration_ms"],
            fallback=parse_meta["fallback"],
        )

        return DocumentUnderstandingResult(
            parser=parser,
            markdown_storage_path=keys["markdown_storage_path"],
            layout_metadata=layout_metadata,
            stage_metadata=stage_metadata,
            artifact_keys=artifact_keys,
        )

    def rollback_artifacts(self, artifact_keys: tuple[str, ...]) -> None:
        """Best-effort delete of uploaded objects after a downstream failure."""
        for key in reversed(artifact_keys):
            logger.warning("Rolling back artifact upload", object_key=key)
            self._storage.delete_object(key)

    def _parse_with_policy(
        self,
        *,
        data: bytes,
        storage_path: str,
        file_type: FileType,
        document_version_id: UUID,
    ) -> tuple[ParseOutput, dict[str, Any]]:
        requested = self._parser.parser_name
        try:
            output = self._parser.parse(
                data=data,
                storage_path=storage_path,
                file_type=file_type,
            )
        except Exception as exc:
            if not should_fallback_to_local_ocr(exc, fallback_enabled=bool(self._fallback_parser)):
                raise _map_primary_parser_error(exc, settings=self._settings) from exc

            reason = _fallback_reason(exc)
            diagnostics = _timeout_diagnostics(exc, settings=self._settings)
            logger.warning(
                "llamaparse_fallback_started",
                document_version_id=str(document_version_id),
                fallback_parser=PARSER_LOCAL_OCR,
                reason=reason,
                **{k: v for k, v in diagnostics.items() if v is not None},
            )
            assert self._fallback_parser is not None
            try:
                output = self._fallback_parser.parse(
                    data=data,
                    storage_path=storage_path,
                    file_type=file_type,
                )
            except DataPipelineError:
                raise
            except Exception as fallback_exc:
                raise DataPipelineError(
                    f"Local OCR fallback failed after LlamaParse {reason}: {fallback_exc}",
                    user_message=USER_PARSE_FAILED,
                    diagnostics={
                        "requested_parser": requested,
                        "actual_parser": None,
                        "fallback": True,
                        "fallback_reason": reason,
                        **diagnostics,
                    },
                ) from fallback_exc

            logger.info(
                "llamaparse_fallback_completed",
                document_version_id=str(document_version_id),
                parser=PARSER_LOCAL_OCR,
                duration_ms=output.parse_duration_ms,
                page_count=output.reported_page_count,
                segment_count=_count_segments(output.item_pages),
                reason=reason,
            )
            return output, {
                "requested_parser": requested,
                "actual_parser": PARSER_LOCAL_OCR,
                "fallback": True,
                "fallback_reason": reason,
                "llamaparse_job_id": diagnostics.get("llamaparse_job_id"),
                "llamaparse_attempts": diagnostics.get("llamaparse_attempts"),
                "llamaparse_timeout_seconds": diagnostics.get("llamaparse_timeout_seconds"),
                "client_timeout": diagnostics.get("client_timeout"),
                "remote_status": diagnostics.get("remote_status"),
            }

        return output, {
            "requested_parser": requested,
            "actual_parser": requested,
            "fallback": False,
            "fallback_reason": None,
            "llamaparse_job_id": output.job_id,
            "llamaparse_attempts": (
                output.attempts if requested == PARSER_LLAMAPARSE else None
            ),
            "llamaparse_timeout_seconds": None,
            "client_timeout": None,
            "remote_status": None,
        }

    def _validate_inputs(self, *, version: DocumentVersion, document: Document) -> None:
        if not version.storage_path or not version.storage_path.strip():
            raise DataPipelineError(
                f"document_version {version.id} has no storage_path — cannot parse",
                user_message=USER_PARSE_FAILED,
            )
        if document.file_type not in SUPPORTED_FILE_TYPES:
            raise DataPipelineError(
                f"Unsupported file type for document understanding: {document.file_type.value}",
                user_message=USER_PARSE_FAILED,
            )

    def _should_skip_reparse(self, version: DocumentVersion) -> bool:
        return bool(
            version.markdown_storage_path
            and version.markdown_storage_path.strip()
            and version.layout_metadata
        )

    def _result_from_existing(
        self,
        *,
        document_version_id: UUID,
        version: DocumentVersion,
        document: Document,
        started: float,
    ) -> DocumentUnderstandingResult:
        layout = version.layout_metadata or {}
        metrics_dict = layout.get("metrics") or {}
        parser = version.parser or layout.get("parser") or self._parser.parser_name
        layout_artifact_key = layout.get("layout_artifact_key") or pipeline_artifact_key(
            version.storage_path,
            LAYOUT_ARTIFACT,
        )
        block_count = layout.get("block_count", len(layout.get("blocks") or []))

        stage_metadata = {
            "document_version_id": str(document_version_id),
            "file_type": document.file_type.value,
            "parser": parser,
            "requested_parser": parser,
            "actual_parser": parser,
            "fallback": False,
            "fallback_reason": None,
            "layout_source": layout.get("source"),
            "llamaparse_job_id": layout.get("job_id"),
            "llamaparse_tier": layout.get("tier"),
            "llamaparse_attempts": None,
            "llamaparse_timeout_seconds": None,
            "client_timeout": None,
            "remote_status": None,
            "parse_duration_ms": 0,
            "page_count": resolve_page_count_from_layout(layout, document.file_type),
            "section_count": layout.get("section_count", 0),
            "block_count": block_count,
            "markdown_bytes": metrics_dict.get("char_count", 0),
            "heading_counts_by_level": metrics_dict.get("heading_counts_by_level", {}),
            "heading_count": metrics_dict.get("heading_count", 0),
            "table_count": metrics_dict.get("table_count", 0),
            "figure_count": metrics_dict.get("figure_count", 0),
            "word_count": metrics_dict.get("word_count", 0),
            "char_count": metrics_dict.get("char_count", 0),
            "markdown_storage_path": version.markdown_storage_path,
            "layout_artifact_key": layout_artifact_key,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

        return DocumentUnderstandingResult(
            parser=parser,
            markdown_storage_path=version.markdown_storage_path,
            layout_metadata=layout,
            stage_metadata=stage_metadata,
            artifact_keys=(),
        )

    def _download_bytes(self, storage_path: str) -> bytes:
        try:
            data = self._storage.download_bytes(storage_path)
        except S3Error as exc:
            code = getattr(exc, "code", "") or ""
            if code in {"NoSuchKey", "NoSuchBucket", "NotFound"}:
                raise DataPipelineError(
                    f"Source file missing in object storage: {storage_path}",
                    user_message=USER_PARSE_FAILED,
                ) from exc
            raise TransientPipelineError(f"MinIO download failed: {exc}") from exc
        except OSError as exc:
            raise TransientPipelineError(f"MinIO download I/O error: {exc}") from exc

        if not data:
            raise DataPipelineError(
                "Source file in object storage is empty",
                user_message=USER_PARSE_FAILED,
            )
        return data

    def _persist_outputs(
        self,
        *,
        document_version_id: UUID,
        storage_path: str,
        parser: str,
        markdown: str,
        analysis: LayoutAnalysis,
        metrics: MarkdownMetrics,
        job_id: str | None,
    ) -> dict[str, Any]:
        """Write artifacts sequentially; rollback prior uploads on mid-flight failure."""
        uploaded_keys: list[str] = []
        try:
            logger.info("Persist markdown", document_version_id=str(document_version_id))
            markdown_key = save_text_output(
                self._storage,
                storage_path=storage_path,
                output_name=MARKDOWN_ARTIFACT,
                text=markdown,
            )
            uploaded_keys.append(markdown_key)

            logger.info("Persist layout", document_version_id=str(document_version_id))
            layout_key = save_json_artifact(
                self._storage,
                storage_path=storage_path,
                artifact_name=LAYOUT_ARTIFACT,
                payload=build_layout_artifact(
                    document_version_id=str(document_version_id),
                    analysis=analysis,
                    metrics=metrics,
                    parser=parser,
                    job_id=job_id,
                ),
            )
            uploaded_keys.append(layout_key)
        except S3Error as exc:
            self.rollback_artifacts(tuple(uploaded_keys))
            raise TransientPipelineError(f"Failed to store parse outputs: {exc}") from exc
        except OSError as exc:
            self.rollback_artifacts(tuple(uploaded_keys))
            raise TransientPipelineError(f"MinIO upload I/O error: {exc}") from exc

        return {
            "markdown_storage_path": markdown_key,
            "layout_artifact_key": layout_key,
        }


def should_fallback_to_local_ocr(
    exc: BaseException,
    *,
    fallback_enabled: bool,
) -> bool:
    """Return True when LlamaParse failure is eligible for local OCR fallback."""
    if not fallback_enabled:
        return False
    if isinstance(exc, LlamaParseTimeoutError):
        return True
    if isinstance(exc, LlamaParseCircuitOpenError):
        return True
    if isinstance(exc, LlamaParseServiceError):
        return True
    if isinstance(exc, LlamaParseRequestError):
        # Auth / billing / rate-limit must surface as configuration/quota errors.
        if exc.status_code in _NO_FALLBACK_STATUS_CODES:
            return False
        # Invalid request / unsupported file / FAILED job — do not hide behind OCR.
        return False
    return False


def build_document_understanding_service(
    *,
    storage: MinioStorageAdapter,
    settings: Settings,
    llamaparse_client: LlamaParseClient | None = None,
) -> DocumentUnderstandingService:
    """Factory wiring the configured parser into a service instance."""
    parser = resolve_document_parser(
        settings=settings,
        llamaparse_client=llamaparse_client,
    )
    fallback: DocumentParser | None = None
    if (
        settings.document_parser == "llamaparse"
        and settings.llamaparse_fallback_to_local_ocr
    ):
        fallback = LocalOcrDocumentParser()
    return DocumentUnderstandingService(
        storage=storage,
        settings=settings,
        parser=parser,
        fallback_parser=fallback,
    )


def resolve_document_parser(
    *,
    settings: Settings,
    llamaparse_client: LlamaParseClient | None = None,
) -> DocumentParser:
    """Select and validate the configured document parser."""
    if settings.document_parser == "llamaparse":
        api_key = (settings.llamaparse_api_key or "").strip()
        if not api_key:
            raise DataPipelineError(
                "Document parser configuration error: DOCUMENT_PARSER=llamaparse "
                "requires LLAMAPARSE_API_KEY",
            )
        client = llamaparse_client or LlamaParseClient(settings)
        return LlamaParseDocumentParser(client=client, settings=settings)

    if settings.document_parser == "local":
        return LocalOcrDocumentParser()

    raise DataPipelineError(
        f"Document parser configuration error: unsupported DOCUMENT_PARSER="
        f"{settings.document_parser!r} (expected 'llamaparse' or 'local')"
    )


def resolve_page_count_from_layout(layout: dict[str, Any], file_type: FileType) -> int:
    """Derive page_count from stored layout_metadata during idempotent skip."""
    page_count = layout.get("page_count") or 0
    section_count = layout.get("section_count") or 0
    if file_type in PAGINATED_FILE_TYPES:
        return max(1, int(page_count))
    return max(1, int(section_count))


def _map_primary_parser_error(exc: BaseException, *, settings: Settings) -> DataPipelineError:
    """Map LlamaParse / local failures to terminal DataPipelineError with user text."""
    if isinstance(exc, DataPipelineError):
        return exc
    if isinstance(exc, LlamaParseCircuitOpenError):
        return DataPipelineError(
            "LlamaParse circuit breaker open",
            user_message=USER_PARSE_FAILED,
            diagnostics={"fallback": False, "fallback_reason": "circuit_open"},
        )
    if isinstance(exc, LlamaParseTimeoutError):
        diagnostics = _timeout_diagnostics(exc, settings=settings)
        return DataPipelineError(
            str(exc),
            user_message=USER_PARSE_FAILED,
            diagnostics={
                "requested_parser": PARSER_LLAMAPARSE,
                "actual_parser": None,
                "fallback": False,
                "fallback_reason": "timeout",
                **diagnostics,
            },
        )
    if isinstance(exc, LlamaParseServiceError):
        return DataPipelineError(
            f"LlamaParse unavailable after HTTP retries "
            f"(max_retries={settings.llamaparse_max_retries}): {exc}",
            user_message=USER_PARSE_FAILED,
            diagnostics={
                "requested_parser": PARSER_LLAMAPARSE,
                "fallback": False,
                "fallback_reason": "service_unavailable",
                "status_code": exc.status_code,
            },
        )
    if isinstance(exc, LlamaParseRequestError):
        if exc.status_code in {401, 403}:
            return DataPipelineError(
                f"LlamaParse authentication/configuration error: {exc}",
                diagnostics={
                    "requested_parser": PARSER_LLAMAPARSE,
                    "fallback": False,
                    "fallback_reason": "authentication",
                    "status_code": exc.status_code,
                },
            )
        if exc.status_code in {402, 429}:
            return DataPipelineError(
                f"LlamaParse quota/billing error: {exc}",
                diagnostics={
                    "requested_parser": PARSER_LLAMAPARSE,
                    "fallback": False,
                    "fallback_reason": "quota",
                    "status_code": exc.status_code,
                },
            )
        return DataPipelineError(
            f"LlamaParse rejected the document: {exc}",
            user_message=USER_PARSE_FAILED,
            diagnostics={
                "requested_parser": PARSER_LLAMAPARSE,
                "fallback": False,
                "fallback_reason": "unsupported_or_invalid",
                "status_code": exc.status_code,
            },
        )
    if isinstance(exc, LlamaParseError):
        return DataPipelineError(
            f"LlamaParse failed: {exc}",
            user_message=USER_PARSE_FAILED,
        )
    return DataPipelineError(str(exc), user_message=USER_PARSE_FAILED)


def _fallback_reason(exc: BaseException) -> str:
    if isinstance(exc, LlamaParseTimeoutError):
        return "timeout"
    if isinstance(exc, LlamaParseCircuitOpenError):
        return "circuit_open"
    if isinstance(exc, LlamaParseServiceError):
        return "service_unavailable"
    return "unknown"


def _timeout_diagnostics(exc: BaseException, *, settings: Settings) -> dict[str, Any]:
    if isinstance(exc, LlamaParseTimeoutError):
        return {
            "llamaparse_job_id": exc.job_id,
            "llamaparse_attempts": 1,
            "llamaparse_timeout_seconds": exc.budget_seconds
            or settings.llamaparse_timeout_seconds,
            "client_timeout": bool(exc.client_timeout),
            "remote_status": exc.remote_status,
        }
    return {
        "llamaparse_job_id": None,
        "llamaparse_attempts": None,
        "llamaparse_timeout_seconds": settings.llamaparse_timeout_seconds,
        "client_timeout": isinstance(exc, LlamaParseTimeoutError),
        "remote_status": None,
    }


def _count_segments(item_pages: list[dict[str, Any]]) -> int:
    total = 0
    for page in item_pages:
        items = page.get("items")
        if isinstance(items, list):
            total += len(items)
    return total


def _segments_to_item_pages(segments: list[Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    current_page: int | None = -1

    for segment in segments:
        text = (getattr(segment, "text", "") or "").strip()
        if not text:
            continue
        page_number = getattr(segment, "page_number", None)
        if not pages or page_number != current_page:
            pages.append({"page_number": page_number, "items": []})
            current_page = page_number

        item: dict[str, Any] = {
            "type": getattr(segment, "block_type", None) or "paragraph",
            "md": text,
        }
        level = getattr(segment, "heading_level", None)
        if level:
            item["lvl"] = level
        bbox = getattr(segment, "bbox", None)
        if bbox:
            item["bbox"] = list(bbox)
        pages[-1]["items"].append(item)

    return pages


def _markdown_from_item_pages(item_pages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for page in item_pages:
        for item in page["items"]:
            text = item["md"]
            if item["type"] == "heading":
                level = min(6, max(1, int(item.get("lvl") or 1)))
                parts.append(f"{'#' * level} {text}")
            else:
                parts.append(text)
    return "\n\n".join(parts)
