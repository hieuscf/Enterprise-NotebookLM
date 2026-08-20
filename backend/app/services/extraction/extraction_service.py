# =============================================================================
# File: extraction_service.py
# Module/Service: Extraction Service (FR7)
# Layer: Service
# Purpose: Async Information Extraction request + generation for document versions (UC6).
# Responsibilities:
#   - request_extraction: create processing row, commit, enqueue Celery (no LLM)
#   - process_extraction: generate into existing row using persisted source_version_id
#   - list / get / delete for HTTP API
#   - extract_information: in-process create+process for sync / Part 4 tests
# Dependencies:
#   - DocumentRepository, RetrievalRepository, ExtractionRepository
#   - chat_llm adapter, model_tiering, count_tokens
#   - app.workers.extractions (Celery enqueue)
# Public Exports:
#   - ExtractionService, ExtractionServiceError
# Database/Table: extractions, documents, document_versions, document_chunks,
#   entities
# Related Modules: prompts, result_schemas, timeline_sort, OpenAPI Extraction
# Important Notes:
#   - HTTP path must not call the LLM; generation runs in process_extraction only.
#   - Celery MUST use source_version_id (never re-read current_version_id).
#   - Standard extraction_type=entities reuses Graph/LightRAG entities
#     (Entity.source_version_id) — ZERO LLM calls (REUSE_EXISTING_ENTITIES).
#   - LLM_ENTITY_EXTRACTION is an explicit isolated fallback mode only.
#   - LLM paths use extract_structured_json_async + Pydantic validation.
#   - Extraction is version-bound; never mix chunks across versions.
# =============================================================================

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.chat_llm import extract_structured_json_async, resolve_chat_llm
from app.adapters.llm_result import StructuredLlmResult
from app.ai.tokens import count_tokens
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.artifacts import Extraction
from app.models.documents import Document, DocumentVersion
from app.models.enums import (
    DocumentVersionStatus,
    EntityExtractionMode,
    ExtractionOutputFormat,
    ExtractionStatus,
    ExtractionType,
    TargetLanguage,
)
from app.repositories.documents import DocumentRepository
from app.repositories.extractions import ExtractionRepository
from app.repositories.retrieval import ChunkHydrationRow, RetrievalRepository
from app.services.chat.model_tiering import (
    estimate_answer_cost_usd,
    model_context_window,
    select_answer_model,
)
from app.services.extraction.prompts import (
    build_figures_prompts,
    build_llm_entity_prompts,
    build_table_prompts,
    build_timeline_prompts,
)
from app.services.extraction.result_schemas import (
    EntitiesExtractionResult,
    EntityItem,
    FiguresExtractionResult,
    TableExtractionResult,
    TimelineExtractionResult,
    entities_result_to_dict,
    figures_result_to_dict,
    table_result_to_dict,
    timeline_result_to_dict,
    to_table_representation,
)
from app.services.extraction.timeline_sort import sort_timeline_events

logger = get_logger(__name__)

PromptBuilder = Callable[..., tuple[str, str]]
EnqueueFn = Callable[[uuid.UUID], None]


class ExtractionServiceError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ExtractionService:
    """Application service for FR7 Information Extraction (request + generation)."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        documents: DocumentRepository,
        retrieval: RetrievalRepository,
        extractions: ExtractionRepository,
        llm_call: Any | None = None,
        enqueue: bool = True,
        enqueue_fn: EnqueueFn | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._documents = documents
        self._retrieval = retrieval
        self._extractions = extractions
        self._llm_call = llm_call
        self._enqueue = enqueue
        self._enqueue_fn = enqueue_fn
        self._llm_call_count = 0

    @property
    def llm_call_count(self) -> int:
        """Number of LLM invocations in this service instance (tests)."""
        return self._llm_call_count

    # ------------------------------------------------------------------
    # HTTP API operations
    # ------------------------------------------------------------------

    async def request_extraction(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        extraction_type: ExtractionType,
        output_format: ExtractionOutputFormat = ExtractionOutputFormat.json,
        created_by: uuid.UUID,
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> Extraction:
        """Create processing Extraction, commit, enqueue Celery — no LLM in-request."""
        if extraction_type not in ExtractionType:
            raise ExtractionServiceError(
                "invalid_extraction_type",
                f"Unsupported extraction_type: {extraction_type}",
                status_code=422,
            )
        if output_format not in ExtractionOutputFormat:
            raise ExtractionServiceError(
                "invalid_output_format",
                f"Unsupported output_format: {output_format}",
                status_code=422,
            )

        document, version = await self._resolve_ready_current_version(
            workspace_id=workspace_id,
            document_id=document_id,
        )

        # Capture authoritative source version BEFORE enqueue / any later version flip.
        source_version_id = version.id
        row = await self._extractions.create_processing(
            document_id=document.id,
            created_by=created_by,
            source_version_id=source_version_id,
            extraction_type=extraction_type,
            output_format=output_format,
            target_language=target_language,
        )
        # Commit before enqueue so the worker can see the row (documents pattern).
        await self._session.commit()

        try:
            self._enqueue_extraction(row.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("extraction_enqueue_failed", extraction_id=str(row.id))
            await self._extractions.mark_failed(extraction_id=row.id)
            await self._session.commit()
            raise ExtractionServiceError(
                "enqueue_failed",
                "Failed to schedule extraction generation",
                status_code=503,
            ) from exc

        # Refresh after commit so response reflects persisted processing state.
        refreshed = await self._extractions.get_by_id(row.id)
        return refreshed or row

    async def list_extractions(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[Extraction]:
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise ExtractionServiceError("not_found", "Document not found", status_code=404)
        return await self._extractions.list_for_document(
            workspace_id=workspace_id,
            document_id=document_id,
        )

    async def get_extraction(
        self,
        *,
        workspace_id: uuid.UUID,
        extraction_id: uuid.UUID,
    ) -> Extraction:
        row = await self._extractions.get(
            workspace_id=workspace_id, extraction_id=extraction_id
        )
        if row is None:
            raise ExtractionServiceError("not_found", "Extraction not found", status_code=404)
        return row

    async def delete_extraction(
        self,
        *,
        workspace_id: uuid.UUID,
        extraction_id: uuid.UUID,
    ) -> None:
        row = await self._extractions.get(
            workspace_id=workspace_id, extraction_id=extraction_id
        )
        if row is None:
            raise ExtractionServiceError("not_found", "Extraction not found", status_code=404)
        await self._extractions.delete(row)

    # ------------------------------------------------------------------
    # Celery / generation
    # ------------------------------------------------------------------

    async def process_extraction(
        self,
        extraction_id: uuid.UUID,
        *,
        entity_mode: EntityExtractionMode = EntityExtractionMode.REUSE_EXISTING_ENTITIES,
    ) -> Extraction | None:
        """Generate into an existing processing Extraction using source_version_id.

        Idempotent:
          - missing / deleted → None (exit safely)
          - not processing → return row unchanged (no regenerate)
        """
        row = await self._extractions.get_by_id(extraction_id)
        if row is None:
            logger.info("extraction_process_missing", extraction_id=str(extraction_id))
            return None
        if row.status != ExtractionStatus.processing:
            logger.info(
                "extraction_process_skip_status",
                extraction_id=str(extraction_id),
                status=row.status.value,
            )
            return row

        document = await self._documents.get_document_by_id(row.document_id)
        if document is None:
            await self._extractions.mark_failed(extraction_id=row.id)
            return await self._extractions.get_by_id(row.id)

        workspace_id = document.workspace_id
        version = await self._documents.get_version(
            workspace_id, row.document_id, row.source_version_id
        )
        if version is None:
            await self._fail_safe(row.id, "source_version_missing")
            return await self._extractions.get_by_id(row.id)

        try:
            result = await self._run_strategy(
                workspace_id=workspace_id,
                document_id=row.document_id,
                document_title=document.title or "",
                source_version_id=row.source_version_id,
                extraction_type=row.extraction_type,
                output_format=row.output_format,
                target_language=row.target_language,
                entity_mode=entity_mode,
            )
        except ExtractionServiceError as exc:
            logger.warning(
                "extraction_generation_failed",
                extraction_id=str(row.id),
                code=exc.code,
            )
            await self._extractions.mark_failed(extraction_id=row.id)
            return await self._extractions.get_by_id(row.id)
        except Exception:  # noqa: BLE001
            logger.exception("extraction_generation_unexpected", extraction_id=str(row.id))
            await self._extractions.mark_failed(extraction_id=row.id)
            return await self._extractions.get_by_id(row.id)

        updated = await self._extractions.update_generation_result(
            extraction_id=row.id,
            result_json=result["result_json"],
            model_used=result["model_used"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            cost_usd=result["cost_usd"],
            latency_ms=result["latency_ms"],
        )
        if not updated:
            # Race: deleted or status flipped while generating.
            logger.info("extraction_process_race_skip", extraction_id=str(row.id))
            return await self._extractions.get_by_id(row.id)

        final = await self._extractions.get_by_id(row.id)
        logger.info(
            "extraction_generated",
            extraction_id=str(row.id),
            extraction_type=row.extraction_type.value,
            source_version_id=str(row.source_version_id),
            model_used=result["model_used"],
            llm_calls=self._llm_call_count,
        )
        return final

    async def extract_information(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        extraction_type: ExtractionType,
        output_format: ExtractionOutputFormat = ExtractionOutputFormat.json,
        created_by: uuid.UUID,
        target_language: TargetLanguage = TargetLanguage.vi,
        entity_mode: EntityExtractionMode = EntityExtractionMode.REUSE_EXISTING_ENTITIES,
    ) -> Extraction:
        """In-process create+process (tests / sync callers). Still one Extraction row."""
        if extraction_type not in ExtractionType:
            raise ExtractionServiceError(
                "invalid_extraction_type",
                f"Unsupported extraction_type: {extraction_type}",
                status_code=422,
            )
        if output_format not in ExtractionOutputFormat:
            raise ExtractionServiceError(
                "invalid_output_format",
                f"Unsupported output_format: {output_format}",
                status_code=422,
            )

        document, version = await self._resolve_ready_current_version(
            workspace_id=workspace_id,
            document_id=document_id,
        )
        row = await self._extractions.create_processing(
            document_id=document.id,
            created_by=created_by,
            source_version_id=version.id,
            extraction_type=extraction_type,
            output_format=output_format,
            target_language=target_language,
        )
        await self._session.flush()
        final = await self.process_extraction(row.id, entity_mode=entity_mode)
        if final is None or final.status != ExtractionStatus.completed:
            raise ExtractionServiceError(
                "llm_failed",
                "Extraction generation failed",
                status_code=502,
            )
        return final

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enqueue_extraction(self, extraction_id: uuid.UUID) -> None:
        if not self._enqueue:
            return
        if self._enqueue_fn is not None:
            self._enqueue_fn(extraction_id)
            return
        from app.workers.extractions import generate_extraction as generate_extraction_task

        generate_extraction_task.delay(str(extraction_id))

    async def _fail_safe(self, extraction_id: uuid.UUID, reason: str) -> None:
        logger.warning(
            "extraction_mark_failed", extraction_id=str(extraction_id), reason=reason
        )
        await self._extractions.mark_failed(extraction_id=extraction_id)

    async def _resolve_ready_current_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> tuple[Document, DocumentVersion]:
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise ExtractionServiceError("not_found", "Document not found", status_code=404)
        if document.current_version_id is None:
            raise ExtractionServiceError(
                "no_current_version",
                "Document has no current version",
                status_code=409,
            )

        version = await self._documents.get_version(
            workspace_id, document_id, document.current_version_id
        )
        if version is None:
            raise ExtractionServiceError(
                "no_current_version",
                "Current document version not found",
                status_code=409,
            )
        if version.status != DocumentVersionStatus.ready:
            raise ExtractionServiceError(
                "version_not_ready",
                f"Current version status is {version.status.value}; must be ready",
                status_code=409,
            )
        return document, version

    async def _run_strategy(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        document_title: str,
        source_version_id: uuid.UUID,
        extraction_type: ExtractionType,
        output_format: ExtractionOutputFormat,
        target_language: TargetLanguage = TargetLanguage.vi,
        entity_mode: EntityExtractionMode = EntityExtractionMode.REUSE_EXISTING_ENTITIES,
    ) -> dict[str, Any]:
        """Dispatch type strategy for a pinned source_version_id (no Extraction insert)."""
        chunks = await self._retrieval.list_chunks_for_document(
            workspace_id,
            document_id,
            version_id=source_version_id,
        )
        # Entity reuse does not require chunks; LLM paths do.
        needs_chunks = not (
            extraction_type == ExtractionType.entities
            and entity_mode == EntityExtractionMode.REUSE_EXISTING_ENTITIES
        )
        if needs_chunks and not chunks:
            raise ExtractionServiceError(
                "no_chunks",
                "Source document version has no chunks to extract from",
                status_code=409,
            )

        if extraction_type == ExtractionType.entities:
            if entity_mode == EntityExtractionMode.REUSE_EXISTING_ENTITIES:
                canonical, meta = await self._extract_entities_reuse(
                    workspace_id=workspace_id,
                    source_version_id=source_version_id,
                )
            elif entity_mode == EntityExtractionMode.LLM_ENTITY_EXTRACTION:
                canonical, meta = await self._extract_via_llm(
                    extraction_type=ExtractionType.entities,
                    document_title=document_title,
                    chunks=chunks,
                    target_language=target_language,
                )
            else:
                raise ExtractionServiceError(
                    "invalid_entity_mode",
                    f"Unsupported entity_mode: {entity_mode}",
                    status_code=422,
                )
        elif extraction_type == ExtractionType.table:
            canonical, meta = await self._extract_via_llm(
                extraction_type=ExtractionType.table,
                document_title=document_title,
                chunks=chunks,
                target_language=target_language,
            )
        elif extraction_type == ExtractionType.figures:
            canonical, meta = await self._extract_via_llm(
                extraction_type=ExtractionType.figures,
                document_title=document_title,
                chunks=chunks,
                target_language=target_language,
            )
        elif extraction_type == ExtractionType.timeline:
            canonical, meta = await self._extract_via_llm(
                extraction_type=ExtractionType.timeline,
                document_title=document_title,
                chunks=chunks,
                target_language=target_language,
            )
        else:
            raise ExtractionServiceError(
                "invalid_extraction_type",
                f"Unsupported extraction_type: {extraction_type}",
                status_code=422,
            )

        result_json = self._apply_output_format(
            canonical,
            extraction_type=extraction_type,
            output_format=output_format,
        )
        return {
            "result_json": result_json,
            "model_used": meta["model_used"],
            "prompt_tokens": meta["prompt_tokens"],
            "completion_tokens": meta["completion_tokens"],
            "cost_usd": meta["cost_usd"],
            "latency_ms": meta["latency_ms"],
        }

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    async def _extract_entities_reuse(
        self,
        *,
        workspace_id: uuid.UUID,
        source_version_id: uuid.UUID,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """REUSE_EXISTING_ENTITIES — no LLM, version-scoped Graph entities only."""
        entities = await self._extractions.list_entities_for_version(
            workspace_id=workspace_id,
            source_version_id=source_version_id,
        )
        result = EntitiesExtractionResult(
            entities=[
                EntityItem(
                    id=e.id,
                    name=e.name,
                    type=e.type,
                    description=e.description,
                )
                for e in entities
            ]
        )
        meta = {
            "model_used": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": Decimal("0"),
            "latency_ms": None,
        }
        return entities_result_to_dict(result), meta

    async def _extract_via_llm(
        self,
        *,
        extraction_type: ExtractionType,
        document_title: str,
        chunks: list[ChunkHydrationRow],
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if resolve_chat_llm(self._settings) is None and self._llm_call is None:
            raise ExtractionServiceError(
                "llm_not_configured",
                "Chat LLM provider is not configured",
                status_code=503,
            )

        model = select_answer_model(
            self._settings,
            agent_triggered=False,
            prefer_strong=extraction_type
            in {ExtractionType.table, ExtractionType.timeline},
        )
        batches = self._batch_chunks_for_context(
            chunks,
            model=model,
            extraction_type=extraction_type,
            document_title=document_title,
            target_language=target_language,
        )
        if not batches:
            raise ExtractionServiceError(
                "no_chunks",
                "Source document version has no chunks to extract from",
                status_code=409,
            )

        prompt_tokens = 0
        completion_tokens = 0
        cost_usd = Decimal("0")
        model_used: str | None = None
        started = time.perf_counter()
        partials: list[dict[str, Any]] = []

        for batch in batches:
            llm = await self._call_llm(
                extraction_type=extraction_type,
                document_title=document_title,
                chunks=batch,
                model=model,
                target_language=target_language,
            )
            model_used = llm.model
            prompt_tokens += int(llm.input_tokens)
            completion_tokens += int(llm.output_tokens)
            cost_usd += Decimal(str(llm.estimated_cost_usd))
            validated = self._validate_llm_payload(
                extraction_type=extraction_type,
                data=llm.data,
                chunks=batch,
            )
            partials.append(validated)

        latency_ms = int((time.perf_counter() - started) * 1000)
        merged = self._merge_partials(extraction_type, partials, chunks=chunks)
        meta = {
            "model_used": model_used,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
        }
        return merged, meta

    async def _call_llm(
        self,
        *,
        extraction_type: ExtractionType,
        document_title: str,
        chunks: list[ChunkHydrationRow],
        model: str,
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> StructuredLlmResult:
        builder = self._prompt_builder(extraction_type)
        system, user = builder(
            document_title=document_title,
            chunks=chunks,
            target_language=target_language,
        )
        call_kwargs = {
            "system": system,
            "user": user,
            "model": model,
            "max_tokens": int(self._settings.extraction_max_output_tokens),
            "temperature": float(self._settings.chat_answer_temperature),
            "top_p": float(self._settings.chat_answer_top_p),
            "timeout_seconds": float(self._settings.extraction_timeout_seconds),
            "cost_estimator": lambda input_tokens, output_tokens: estimate_answer_cost_usd(
                self._settings,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        }
        try:
            self._llm_call_count += 1
            if self._llm_call is not None:
                return await self._llm_call(**call_kwargs)
            return await extract_structured_json_async(
                settings=self._settings,
                **call_kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise ExtractionServiceError(
                "llm_failed",
                "Extraction generation failed",
                status_code=502,
            ) from exc

    def _prompt_builder(self, extraction_type: ExtractionType) -> PromptBuilder:
        if extraction_type == ExtractionType.table:
            return build_table_prompts
        if extraction_type == ExtractionType.figures:
            return build_figures_prompts
        if extraction_type == ExtractionType.timeline:
            return build_timeline_prompts
        if extraction_type == ExtractionType.entities:
            return build_llm_entity_prompts
        raise ExtractionServiceError(
            "invalid_extraction_type",
            f"Unsupported extraction_type: {extraction_type}",
            status_code=422,
        )

    def _validate_llm_payload(
        self,
        *,
        extraction_type: ExtractionType,
        data: dict[str, Any],
        chunks: list[ChunkHydrationRow],
    ) -> dict[str, Any]:
        try:
            if extraction_type == ExtractionType.table:
                return table_result_to_dict(TableExtractionResult.model_validate(data))
            if extraction_type == ExtractionType.figures:
                return figures_result_to_dict(FiguresExtractionResult.model_validate(data))
            if extraction_type == ExtractionType.entities:
                return entities_result_to_dict(EntitiesExtractionResult.model_validate(data))
            if extraction_type == ExtractionType.timeline:
                known = {c.chunk_id for c in chunks}
                result = TimelineExtractionResult.model_validate(data)
                for event in result.events:
                    if event.source_chunk_id not in known:
                        raise ExtractionServiceError(
                            "invalid_structured_output",
                            "Timeline source_chunk_id is not in the provided chunks",
                            status_code=502,
                        )
                return timeline_result_to_dict(result)
        except ValidationError as exc:
            raise ExtractionServiceError(
                "invalid_structured_output",
                "LLM returned structured output that failed schema validation",
                status_code=502,
            ) from exc
        raise ExtractionServiceError(
            "invalid_extraction_type",
            f"Unsupported extraction_type: {extraction_type}",
            status_code=422,
        )

    def _merge_partials(
        self,
        extraction_type: ExtractionType,
        partials: list[dict[str, Any]],
        *,
        chunks: list[ChunkHydrationRow],
    ) -> dict[str, Any]:
        if not partials:
            raise ExtractionServiceError(
                "empty_extraction",
                "No structured extraction result produced",
                status_code=502,
            )
        if len(partials) == 1 and extraction_type != ExtractionType.timeline:
            return partials[0]

        if extraction_type == ExtractionType.table:
            headers = list(partials[0].get("headers") or [])
            rows: list[dict[str, Any]] = []
            seen: set[str] = set()
            for part in partials:
                part_headers = list(part.get("headers") or [])
                if part_headers and not headers:
                    headers = part_headers
                for row in part.get("rows") or []:
                    key = repr(sorted((str(k), repr(v)) for k, v in row.items()))
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
            return table_result_to_dict(
                TableExtractionResult.model_validate({"headers": headers or ["Column"], "rows": rows})
            )

        if extraction_type == ExtractionType.figures:
            figures: list[dict[str, Any]] = []
            for part in partials:
                figures.extend(part.get("figures") or [])
            return figures_result_to_dict(
                FiguresExtractionResult.model_validate({"figures": figures})
            )

        if extraction_type == ExtractionType.entities:
            entities: list[dict[str, Any]] = []
            seen_names: set[tuple[str, str]] = set()
            for part in partials:
                for ent in part.get("entities") or []:
                    key = (str(ent.get("name") or "").lower(), str(ent.get("type") or "").lower())
                    if key in seen_names:
                        continue
                    seen_names.add(key)
                    entities.append(ent)
            return entities_result_to_dict(
                EntitiesExtractionResult.model_validate({"entities": entities})
            )

        if extraction_type == ExtractionType.timeline:
            events: list[dict[str, Any]] = []
            for part in partials:
                events.extend(part.get("events") or [])
            chunk_order = {
                c.chunk_id: (c.chunk_index if c.chunk_index is not None else 10**9)
                for c in chunks
            }
            sorted_events = sort_timeline_events(events, chunk_order=chunk_order)
            return timeline_result_to_dict(
                TimelineExtractionResult.model_validate({"events": sorted_events})
            )

        return partials[0]

    def _apply_output_format(
        self,
        canonical: dict[str, Any],
        *,
        extraction_type: ExtractionType,
        output_format: ExtractionOutputFormat,
    ) -> dict[str, Any]:
        if output_format == ExtractionOutputFormat.json:
            return canonical
        if output_format == ExtractionOutputFormat.table:
            return to_table_representation(
                canonical, extraction_type=extraction_type.value
            )
        raise ExtractionServiceError(
            "invalid_output_format",
            f"Unsupported output_format: {output_format}",
            status_code=422,
        )

    def _batch_chunks_for_context(
        self,
        chunks: list[ChunkHydrationRow],
        *,
        model: str,
        extraction_type: ExtractionType,
        document_title: str,
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> list[list[ChunkHydrationRow]]:
        """Split chunks into batches that fit the model context window."""
        window = model_context_window(self._settings, model=model)
        reserve = int(self._settings.extraction_prompt_reserve_tokens)
        budget = max(512, window - reserve - int(self._settings.extraction_max_output_tokens))

        batches: list[list[ChunkHydrationRow]] = []
        current: list[ChunkHydrationRow] = []
        current_tokens = 0

        # Approximate overhead of instructions for the type.
        builder = self._prompt_builder(extraction_type)
        empty_system, empty_user = builder(
            document_title=document_title,
            chunks=[],
            target_language=target_language,
        )
        overhead = count_tokens(empty_system) + count_tokens(empty_user)

        for chunk in chunks:
            piece = f"[chunk_id={chunk.chunk_id}]\n{(chunk.content or '').strip()}"
            tok = count_tokens(piece)
            if current and current_tokens + tok + overhead > budget:
                batches.append(current)
                current = []
                current_tokens = 0
            if tok + overhead > budget:
                # Oversized single chunk: still send alone (provider may truncate).
                batches.append([chunk])
                continue
            current.append(chunk)
            current_tokens += tok
        if current:
            batches.append(current)
        return batches
