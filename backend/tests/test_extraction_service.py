# =============================================================================
# File: test_extraction_service.py
# Module/Service: Extraction Service (FR7 Part 4)
# Layer: Service
# Purpose: Unit tests for version-bound Information Extraction strategies.
# Responsibilities:
#   - Cover table / figures / timeline LLM structured paths
#   - Cover entities REUSE_EXISTING_ENTITIES (assert ZERO LLM calls)
#   - Cover LLM_ENTITY_EXTRACTION fallback isolation
#   - Cover version isolation, output formats, malformed schema rejection
# Dependencies:
#   - pytest, ExtractionService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres)
# Related Modules: app.services.extraction.extraction_service
# Important Notes: LLM is injected; entity reuse must never call it.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.adapters.llm_result import StructuredLlmResult
from app.core.config import Settings
from app.models.artifacts import Extraction
from app.models.documents import Document, DocumentVersion
from app.models.enums import (
    DocumentVersionStatus,
    EntityExtractionMode,
    ExtractionOutputFormat,
    ExtractionStatus,
    ExtractionType,
    FileType,
)
from app.repositories.extractions import EntityReuseRow
from app.repositories.retrieval import ChunkHydrationRow
from app.services.extraction.extraction_service import (
    ExtractionService,
    ExtractionServiceError,
)
from app.services.extraction.result_schemas import TableExtractionResult
from app.services.extraction.timeline_sort import sort_timeline_events


@dataclass
class FakeSession:
    commits: int = 0

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


@dataclass
class FakeDocumentRepo:
    document: Document | None = None
    version: DocumentVersion | None = None
    versions: dict[uuid.UUID, DocumentVersion] = field(default_factory=dict)

    async def get_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        if self.document is None:
            return None
        if self.document.workspace_id != workspace_id or self.document.id != document_id:
            return None
        return self.document

    async def get_document_by_id(self, document_id: uuid.UUID) -> Document | None:
        if self.document is None or self.document.id != document_id:
            return None
        return self.document

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion | None:
        if self.document is None or self.document.workspace_id != workspace_id:
            return None
        if version_id in self.versions:
            ver = self.versions[version_id]
            return ver if ver.document_id == document_id else None
        if (
            self.version is None
            or self.version.document_id != document_id
            or self.version.id != version_id
        ):
            return None
        return self.version


@dataclass
class FakeRetrievalRepo:
    chunks_by_version: dict[uuid.UUID, list[ChunkHydrationRow]] = field(default_factory=dict)
    last_version_id: uuid.UUID | None = None

    async def list_chunks_for_document(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
    ) -> list[ChunkHydrationRow]:
        del workspace_id, document_id
        self.last_version_id = version_id
        if version_id is not None and version_id in self.chunks_by_version:
            return list(self.chunks_by_version[version_id])
        return []


class FakeExtractionRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Extraction] = {}
        self.entities: list[EntityReuseRow] = []

    async def create_processing(self, **kwargs: Any) -> Extraction:
        row = Extraction(
            id=uuid.uuid4(),
            document_id=kwargs["document_id"],
            created_by=kwargs["created_by"],
            source_version_id=kwargs["source_version_id"],
            extraction_type=kwargs["extraction_type"],
            output_format=kwargs["output_format"],
            status=ExtractionStatus.processing,
            result_json=None,
            model_used=None,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=None,
            created_at=datetime.now(UTC),
        )
        self.rows[row.id] = row
        return row

    async def get_by_id(self, extraction_id: uuid.UUID) -> Extraction | None:
        return self.rows.get(extraction_id)

    async def update_generation_result(self, *, extraction_id: uuid.UUID, **kwargs: Any) -> bool:
        row = self.rows.get(extraction_id)
        if row is None or row.status != ExtractionStatus.processing:
            return False
        row.result_json = kwargs["result_json"]
        row.model_used = kwargs["model_used"]
        row.prompt_tokens = kwargs["prompt_tokens"]
        row.completion_tokens = kwargs["completion_tokens"]
        row.cost_usd = kwargs["cost_usd"]
        row.latency_ms = kwargs["latency_ms"]
        row.status = ExtractionStatus.completed
        return True

    async def mark_failed(self, *, extraction_id: uuid.UUID) -> bool:
        row = self.rows.get(extraction_id)
        if row is None or row.status != ExtractionStatus.processing:
            return False
        row.status = ExtractionStatus.failed
        row.result_json = None
        return True

    async def list_entities_for_version(
        self,
        *,
        workspace_id: uuid.UUID,
        source_version_id: uuid.UUID,
    ) -> list[EntityReuseRow]:
        del workspace_id, source_version_id
        return list(self.entities)


def _doc_bundle(
    *,
    version_status: DocumentVersionStatus = DocumentVersionStatus.ready,
) -> tuple[Document, DocumentVersion, uuid.UUID, uuid.UUID, uuid.UUID]:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    version = DocumentVersion(
        id=ver_id,
        document_id=doc_id,
        uploaded_by=user_id,
        version_number=2,
        storage_path="workspaces/x/documents/y/v2/a.pdf",
        file_size_bytes=10,
        checksum_sha256="a" * 64,
        status=version_status,
        is_current=True,
    )
    document = Document(
        id=doc_id,
        workspace_id=workspace_id,
        title="Report",
        file_type=FileType.pdf,
        current_version_id=ver_id,
    )
    return document, version, workspace_id, user_id, ver_id


def _chunk(
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    workspace_id: uuid.UUID,
    index: int,
    content: str,
) -> ChunkHydrationRow:
    return ChunkHydrationRow(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        document_version_id=version_id,
        workspace_id=workspace_id,
        content=content,
        title="Report",
        chunk_index=index,
    )


def _settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        chat_llm_provider="anthropic",
        chat_answer_light_model="claude-haiku-test",
        chat_answer_strong_model="claude-sonnet-test",
    )


def _service(
    *,
    document: Document,
    version: DocumentVersion,
    versions: dict[uuid.UUID, DocumentVersion] | None = None,
    chunks_by_version: dict[uuid.UUID, list[ChunkHydrationRow]] | None = None,
    entities: list[EntityReuseRow] | None = None,
    llm_call: Any | None = None,
) -> tuple[ExtractionService, FakeRetrievalRepo, FakeExtractionRepo]:
    docs = FakeDocumentRepo(
        document=document,
        version=version,
        versions=versions or {version.id: version},
    )
    retrieval = FakeRetrievalRepo(chunks_by_version=chunks_by_version or {})
    extractions = FakeExtractionRepo()
    if entities is not None:
        extractions.entities = entities
    svc = ExtractionService(
        settings=_settings(),
        session=FakeSession(),  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        retrieval=retrieval,  # type: ignore[arg-type]
        extractions=extractions,  # type: ignore[arg-type]
        llm_call=llm_call,
        enqueue=False,
    )
    return svc, retrieval, extractions


# ---------------------------------------------------------------------------
# TABLE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_extraction_structured_result_and_metadata() -> None:
    document, version, workspace_id, user_id, ver_id = _doc_bundle()
    chunk = _chunk(
        document_id=document.id,
        version_id=ver_id,
        workspace_id=workspace_id,
        index=0,
        content="Year Revenue\n2024 1000",
    )

    async def llm(**_kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={
                "headers": ["Year", "Revenue"],
                "rows": [{"Year": 2024, "Revenue": 1000}],
            },
            model="claude-sonnet-test",
            input_tokens=10,
            output_tokens=20,
            estimated_cost_usd=0.01,
        )

    svc, _, repo = _service(
        document=document,
        version=version,
        chunks_by_version={ver_id: [chunk]},
        llm_call=llm,
    )
    row = await svc.extract_information(
        workspace_id=workspace_id,
        document_id=document.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        created_by=user_id,
    )
    assert row.source_version_id == ver_id
    assert row.result_json["headers"] == ["Year", "Revenue"]
    assert row.result_json["rows"] == [{"Year": 2024, "Revenue": 1000}]
    assert row.model_used == "claude-sonnet-test"
    assert row.prompt_tokens == 10
    assert row.completion_tokens == 20
    assert row.cost_usd == Decimal("0.01")
    assert row.latency_ms is not None
    assert svc.llm_call_count == 1
    assert len(repo.rows) == 1


@pytest.mark.asyncio
async def test_table_malformed_structured_output_rejected() -> None:
    document, version, workspace_id, user_id, ver_id = _doc_bundle()
    chunk = _chunk(
        document_id=document.id,
        version_id=ver_id,
        workspace_id=workspace_id,
        index=0,
        content="table",
    )

    async def llm(**_kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={"headers": [], "rows": "not-a-list"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        )

    svc, _, repo = _service(
        document=document,
        version=version,
        chunks_by_version={ver_id: [chunk]},
        llm_call=llm,
    )
    with pytest.raises(ExtractionServiceError) as exc:
        await svc.extract_information(
            workspace_id=workspace_id,
            document_id=document.id,
            extraction_type=ExtractionType.table,
            created_by=user_id,
        )
    assert exc.value.code == "llm_failed"
    # process_extraction marks the row failed without re-raising domain codes.
    failed = next(iter(repo.rows.values()))
    assert failed.status == ExtractionStatus.failed


def test_table_schema_rejects_duplicate_headers() -> None:
    with pytest.raises(Exception):
        TableExtractionResult.model_validate(
            {"headers": ["A", "A"], "rows": []}
        )


# ---------------------------------------------------------------------------
# FIGURES
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_figures_extraction() -> None:
    document, version, workspace_id, user_id, ver_id = _doc_bundle()
    chunk = _chunk(
        document_id=document.id,
        version_id=ver_id,
        workspace_id=workspace_id,
        index=0,
        content="Revenue was 1200000 USD in FY2025",
    )

    async def llm(**_kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={
                "figures": [
                    {
                        "metric": "Revenue",
                        "value": 1200000,
                        "unit": "USD",
                        "context": "FY2025",
                    }
                ]
            },
            model="claude-haiku-test",
            input_tokens=5,
            output_tokens=8,
            estimated_cost_usd=0.002,
        )

    svc, _, _ = _service(
        document=document,
        version=version,
        chunks_by_version={ver_id: [chunk]},
        llm_call=llm,
    )
    row = await svc.extract_information(
        workspace_id=workspace_id,
        document_id=document.id,
        extraction_type=ExtractionType.figures,
        created_by=user_id,
    )
    fig = row.result_json["figures"][0]
    assert fig["metric"] == "Revenue"
    assert fig["value"] == 1200000
    assert fig["unit"] == "USD"
    assert fig["context"] == "FY2025"
    assert row.source_version_id == ver_id
    assert row.prompt_tokens == 5
    assert row.cost_usd == Decimal("0.002")


# ---------------------------------------------------------------------------
# ENTITIES — reuse (ZERO LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entities_reuse_makes_zero_llm_calls() -> None:
    document, version, workspace_id, user_id, ver_id = _doc_bundle()
    entity_id = uuid.uuid4()

    async def llm(**_kwargs: Any) -> StructuredLlmResult:
        raise AssertionError("LLM must not be called for entity reuse")

    svc, _, _ = _service(
        document=document,
        version=version,
        chunks_by_version={ver_id: []},  # reuse path does not need chunks
        entities=[
            EntityReuseRow(
                id=entity_id,
                name="Acme Corp",
                type="ORGANIZATION",
                description="Customer",
            )
        ],
        llm_call=llm,
    )
    row = await svc.extract_information(
        workspace_id=workspace_id,
        document_id=document.id,
        extraction_type=ExtractionType.entities,
        entity_mode=EntityExtractionMode.REUSE_EXISTING_ENTITIES,
        created_by=user_id,
    )
    assert svc.llm_call_count == 0
    assert row.model_used is None
    assert row.prompt_tokens == 0
    assert row.completion_tokens == 0
    assert row.cost_usd == Decimal("0")
    assert row.latency_ms is None
    assert row.source_version_id == ver_id
    assert row.result_json["entities"] == [
        {
            "id": str(entity_id),
            "name": "Acme Corp",
            "type": "ORGANIZATION",
            "description": "Customer",
        }
    ]


@pytest.mark.asyncio
async def test_entities_llm_fallback_records_metadata() -> None:
    document, version, workspace_id, user_id, ver_id = _doc_bundle()
    chunk = _chunk(
        document_id=document.id,
        version_id=ver_id,
        workspace_id=workspace_id,
        index=0,
        content="Special domain entity XYZ-99",
    )

    async def llm(**_kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={
                "entities": [
                    {
                        "name": "XYZ-99",
                        "type": "DOMAIN_CODE",
                        "description": "Custom code",
                    }
                ]
            },
            model="claude-haiku-test",
            input_tokens=3,
            output_tokens=4,
            estimated_cost_usd=0.001,
        )

    svc, _, _ = _service(
        document=document,
        version=version,
        chunks_by_version={ver_id: [chunk]},
        entities=[],  # reuse data unused in LLM mode
        llm_call=llm,
    )
    row = await svc.extract_information(
        workspace_id=workspace_id,
        document_id=document.id,
        extraction_type=ExtractionType.entities,
        entity_mode=EntityExtractionMode.LLM_ENTITY_EXTRACTION,
        created_by=user_id,
    )
    assert svc.llm_call_count == 1
    assert row.model_used == "claude-haiku-test"
    assert row.prompt_tokens == 3
    assert row.completion_tokens == 4
    assert row.result_json["entities"][0]["name"] == "XYZ-99"


# ---------------------------------------------------------------------------
# TIMELINE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeline_extraction_sorted_with_source_chunk() -> None:
    document, version, workspace_id, user_id, ver_id = _doc_bundle()
    c0 = _chunk(
        document_id=document.id,
        version_id=ver_id,
        workspace_id=workspace_id,
        index=0,
        content="In 2025 the product launched.",
    )
    c1 = _chunk(
        document_id=document.id,
        version_id=ver_id,
        workspace_id=workspace_id,
        index=1,
        content="In 2024 planning started.",
    )

    async def llm(**_kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={
                "events": [
                    {
                        "date_or_period": "2025",
                        "event": "Product launch",
                        "source_chunk_id": str(c0.chunk_id),
                    },
                    {
                        "date_or_period": "2024",
                        "event": "Planning started",
                        "source_chunk_id": str(c1.chunk_id),
                    },
                ]
            },
            model="claude-sonnet-test",
            input_tokens=9,
            output_tokens=11,
            estimated_cost_usd=0.02,
        )

    svc, _, _ = _service(
        document=document,
        version=version,
        chunks_by_version={ver_id: [c0, c1]},
        llm_call=llm,
    )
    row = await svc.extract_information(
        workspace_id=workspace_id,
        document_id=document.id,
        extraction_type=ExtractionType.timeline,
        created_by=user_id,
    )
    events = row.result_json["events"]
    assert [e["date_or_period"] for e in events] == ["2024", "2025"]
    assert events[0]["source_chunk_id"] == str(c1.chunk_id)
    assert row.source_version_id == ver_id
    assert row.model_used == "claude-sonnet-test"


def test_timeline_sort_periods_stable_by_chunk_order() -> None:
    c0 = uuid.uuid4()
    c1 = uuid.uuid4()
    events = [
        {"date_or_period": "sometime", "event": "B", "source_chunk_id": str(c1)},
        {"date_or_period": "sometime", "event": "A", "source_chunk_id": str(c0)},
        {"date_or_period": "2024-01-01", "event": "C", "source_chunk_id": str(c1)},
    ]
    ordered = sort_timeline_events(
        events, chunk_order={c0: 0, c1: 1}
    )
    assert ordered[0]["event"] == "C"
    assert ordered[1]["event"] == "A"
    assert ordered[2]["event"] == "B"


# ---------------------------------------------------------------------------
# Version isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_version_isolation_uses_only_current_version_chunks() -> None:
    document, v2, workspace_id, user_id, v2_id = _doc_bundle()
    v1_id = uuid.uuid4()
    v1 = DocumentVersion(
        id=v1_id,
        document_id=document.id,
        uploaded_by=user_id,
        version_number=1,
        storage_path="workspaces/x/documents/y/v1/a.pdf",
        file_size_bytes=10,
        checksum_sha256="b" * 64,
        status=DocumentVersionStatus.ready,
        is_current=False,
    )
    old_chunk = _chunk(
        document_id=document.id,
        version_id=v1_id,
        workspace_id=workspace_id,
        index=0,
        content="OLD VERSION CONTENT SHOULD NEVER APPEAR",
    )
    new_chunk = _chunk(
        document_id=document.id,
        version_id=v2_id,
        workspace_id=workspace_id,
        index=0,
        content="NEW VERSION",
    )
    seen_contents: list[str] = []

    async def llm(**kwargs: Any) -> StructuredLlmResult:
        user = kwargs.get("user") or ""
        seen_contents.append(user)
        assert "OLD VERSION CONTENT SHOULD NEVER APPEAR" not in user
        assert "NEW VERSION" in user
        return StructuredLlmResult(
            data={"headers": ["Col"], "rows": [{"Col": 1}]},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        )

    svc, retrieval, _ = _service(
        document=document,
        version=v2,
        versions={v1_id: v1, v2_id: v2},
        chunks_by_version={v1_id: [old_chunk], v2_id: [new_chunk]},
        llm_call=llm,
    )
    row = await svc.extract_information(
        workspace_id=workspace_id,
        document_id=document.id,
        extraction_type=ExtractionType.table,
        created_by=user_id,
    )
    assert retrieval.last_version_id == v2_id
    assert row.source_version_id == v2_id
    assert seen_contents


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_output_format_table_for_figures() -> None:
    document, version, workspace_id, user_id, ver_id = _doc_bundle()
    chunk = _chunk(
        document_id=document.id,
        version_id=ver_id,
        workspace_id=workspace_id,
        index=0,
        content="metric",
    )

    async def llm(**_kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={
                "figures": [
                    {
                        "metric": "Revenue",
                        "value": 10,
                        "unit": "USD",
                        "context": "FY",
                    }
                ]
            },
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        )

    svc, _, _ = _service(
        document=document,
        version=version,
        chunks_by_version={ver_id: [chunk]},
        llm_call=llm,
    )
    row = await svc.extract_information(
        workspace_id=workspace_id,
        document_id=document.id,
        extraction_type=ExtractionType.figures,
        output_format=ExtractionOutputFormat.table,
        created_by=user_id,
    )
    assert row.result_json["headers"] == ["metric", "value", "unit", "context"]
    assert row.result_json["rows"][0]["metric"] == "Revenue"
    assert "figures" not in row.result_json


@pytest.mark.asyncio
async def test_output_format_json_keeps_canonical_table() -> None:
    document, version, workspace_id, user_id, ver_id = _doc_bundle()
    chunk = _chunk(
        document_id=document.id,
        version_id=ver_id,
        workspace_id=workspace_id,
        index=0,
        content="t",
    )

    async def llm(**_kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={"headers": ["A"], "rows": [{"A": 1}]},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        )

    svc, _, _ = _service(
        document=document,
        version=version,
        chunks_by_version={ver_id: [chunk]},
        llm_call=llm,
    )
    row = await svc.extract_information(
        workspace_id=workspace_id,
        document_id=document.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        created_by=user_id,
    )
    assert row.result_json == {"headers": ["A"], "rows": [{"A": 1}]}


@pytest.mark.asyncio
async def test_no_chunks_errors_for_llm_paths() -> None:
    document, version, workspace_id, user_id, _ver_id = _doc_bundle()
    svc, _, _ = _service(
        document=document,
        version=version,
        chunks_by_version={},
        llm_call=lambda **_: None,
    )
    with pytest.raises(ExtractionServiceError) as exc:
        await svc.extract_information(
            workspace_id=workspace_id,
            document_id=document.id,
            extraction_type=ExtractionType.table,
            created_by=user_id,
        )
    assert exc.value.code == "llm_failed"
