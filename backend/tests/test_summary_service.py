# =============================================================================
# File: test_summary_service.py
# Module/Service: Summary Service (FR6 Part 1)
# Layer: Service
# Purpose: Unit tests for generate_summary branches (styles, errors, budgeting).
# Responsibilities:
#   - Cover not-found / no-version / not-ready / no-chunks / llm missing
#   - Cover all four styles + by_topic with topics
#   - Cover model tiering prefer_strong + context truncation + persist fields
# Dependencies:
#   - pytest, SummaryService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres)
# Related Modules: app.services.summary.summary_service
# Important Notes: LLM is injected; does not call Anthropic/OpenAI.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.adapters.llm_result import StructuredLlmResult
from app.core.config import Settings
from app.models.artifacts import Summary
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType, SummaryStyle, SummaryType
from app.repositories.retrieval import ChunkHydrationRow
from app.repositories.summaries import TopicContextRow
from app.services.summary.summary_service import SummaryService, SummaryServiceError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeDocumentRepo:
    document: Document | None = None
    version: DocumentVersion | None = None

    async def get_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        if self.document is None:
            return None
        if self.document.workspace_id != workspace_id or self.document.id != document_id:
            return None
        return self.document

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion | None:
        if self.version is None:
            return None
        if (
            self.document is None
            or self.document.workspace_id != workspace_id
            or self.version.document_id != document_id
            or self.version.id != version_id
        ):
            return None
        return self.version


@dataclass
class FakeRetrievalRepo:
    chunks: list[ChunkHydrationRow] | None = None

    async def list_chunks_for_document(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
    ) -> list[ChunkHydrationRow]:
        del workspace_id, document_id, version_id
        return list(self.chunks or [])


@dataclass
class FakeSummaryRepo:
    created: list[Summary]
    topics: list[TopicContextRow]

    def __init__(self) -> None:
        self.created = []
        self.topics = []

    async def create(self, **kwargs: Any) -> Summary:
        row = Summary(
            id=uuid.uuid4(),
            document_id=kwargs["document_id"],
            created_by=kwargs["created_by"],
            source_version_id=kwargs["source_version_id"],
            type=kwargs["type_"],
            content=kwargs["content"],
            model_used=kwargs["model_used"],
            prompt_tokens=kwargs["prompt_tokens"],
            completion_tokens=kwargs["completion_tokens"],
            cost_usd=kwargs["cost_usd"],
            latency_ms=kwargs["latency_ms"],
            created_at=datetime.now(UTC),
        )
        self.created.append(row)
        return row

    async def list_topics_for_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> list[TopicContextRow]:
        del workspace_id, document_version_id
        return list(self.topics)


def _settings(**overrides: Any) -> Settings:
    base = {
        "chat_llm_provider": "anthropic",
        "anthropic_api_key": "test-key",
        "chat_answer_light_model": "claude-light-test",
        "chat_answer_strong_model": "claude-strong-test",
        "chat_answer_light_context_window": 2_000,
        "chat_answer_strong_context_window": 2_000,
        "summary_prompt_reserve_tokens": 200,
        "summary_max_output_tokens": 100,
        "chat_answer_light_input_usd_per_mtok": 1.0,
        "chat_answer_light_output_usd_per_mtok": 2.0,
        "chat_answer_strong_input_usd_per_mtok": 10.0,
        "chat_answer_strong_output_usd_per_mtok": 20.0,
    }
    base.update(overrides)
    return Settings(**base)


def _doc_bundle(
    *,
    status: DocumentVersionStatus = DocumentVersionStatus.ready,
    with_current: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, Document, DocumentVersion]:
    workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    user_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        uploaded_by=user_id,
        version_number=1,
        storage_path="workspaces/x/documents/y/v1/a.pdf",
        file_size_bytes=10,
        checksum_sha256="a" * 64,
        status=status,
        is_current=True,
    )
    document = Document(
        id=document_id,
        workspace_id=workspace_id,
        current_version_id=version_id if with_current else None,
        title="Q1 Report",
        file_type=FileType.pdf,
    )
    return workspace_id, document_id, user_id, document, version


def _chunk(
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    content: str,
    index: int = 0,
) -> ChunkHydrationRow:
    return ChunkHydrationRow(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        document_version_id=version_id,
        workspace_id=workspace_id,
        content=content,
        title="Q1 Report",
        chunk_index=index,
        page_number=1,
    )


def _service(
    *,
    docs: FakeDocumentRepo,
    retrieval: FakeRetrievalRepo,
    summaries: FakeSummaryRepo,
    settings: Settings | None = None,
    llm_result: StructuredLlmResult | None = None,
    llm_error: Exception | None = None,
) -> SummaryService:
    async def _llm(**kwargs: Any) -> StructuredLlmResult:
        del kwargs
        if llm_error is not None:
            raise llm_error
        assert llm_result is not None
        return llm_result

    return SummaryService(
        settings=settings or _settings(),
        documents=docs,  # type: ignore[arg-type]
        retrieval=retrieval,  # type: ignore[arg-type]
        summaries=summaries,  # type: ignore[arg-type]
        llm_call=_llm if (llm_result is not None or llm_error is not None) else None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_summary_document_not_found() -> None:
    svc = _service(
        docs=FakeDocumentRepo(),
        retrieval=FakeRetrievalRepo(),
        summaries=FakeSummaryRepo(),
        llm_result=StructuredLlmResult(
            data={"summary": "x"},
            model="claude-light-test",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        ),
    )
    with pytest.raises(SummaryServiceError) as exc:
        await svc.generate_summary(
            workspace_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            style=SummaryStyle.short,
            created_by=uuid.uuid4(),
        )
    assert exc.value.code == "not_found"
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_generate_summary_no_current_version() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle(with_current=False)
    docs = FakeDocumentRepo(document=document, version=version)
    svc = _service(
        docs=docs,
        retrieval=FakeRetrievalRepo(chunks=[]),
        summaries=FakeSummaryRepo(),
        llm_result=StructuredLlmResult(
            data={"summary": "x"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        ),
    )
    with pytest.raises(SummaryServiceError) as exc:
        await svc.generate_summary(
            workspace_id=workspace_id,
            document_id=document_id,
            style=SummaryStyle.short,
            created_by=user_id,
        )
    assert exc.value.code == "no_current_version"


@pytest.mark.asyncio
async def test_generate_summary_version_not_ready() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle(
        status=DocumentVersionStatus.processing
    )
    docs = FakeDocumentRepo(document=document, version=version)
    svc = _service(
        docs=docs,
        retrieval=FakeRetrievalRepo(
            chunks=[
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=version.id,
                    content="hello",
                )
            ]
        ),
        summaries=FakeSummaryRepo(),
        llm_result=StructuredLlmResult(
            data={"summary": "x"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        ),
    )
    with pytest.raises(SummaryServiceError) as exc:
        await svc.generate_summary(
            workspace_id=workspace_id,
            document_id=document_id,
            style=SummaryStyle.short,
            created_by=user_id,
        )
    assert exc.value.code == "version_not_ready"


@pytest.mark.asyncio
async def test_generate_summary_no_chunks() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
    svc = _service(
        docs=FakeDocumentRepo(document=document, version=version),
        retrieval=FakeRetrievalRepo(chunks=[]),
        summaries=FakeSummaryRepo(),
        llm_result=StructuredLlmResult(
            data={"summary": "x"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        ),
    )
    with pytest.raises(SummaryServiceError) as exc:
        await svc.generate_summary(
            workspace_id=workspace_id,
            document_id=document_id,
            style=SummaryStyle.short,
            created_by=user_id,
        )
    assert exc.value.code == "no_chunks"


@pytest.mark.asyncio
async def test_generate_summary_llm_not_configured() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
    settings = _settings(anthropic_api_key=None)
    svc = _service(
        docs=FakeDocumentRepo(document=document, version=version),
        retrieval=FakeRetrievalRepo(
            chunks=[
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=version.id,
                    content="Revenue grew 10%.",
                )
            ]
        ),
        summaries=FakeSummaryRepo(),
        settings=settings,
    )
    with pytest.raises(SummaryServiceError) as exc:
        await svc.generate_summary(
            workspace_id=workspace_id,
            document_id=document_id,
            style=SummaryStyle.short,
            created_by=user_id,
        )
    assert exc.value.code == "llm_not_configured"
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("style", "expect_strong"),
    [
        (SummaryStyle.short, False),
        (SummaryStyle.bullet_points, False),
        (SummaryStyle.detailed, True),
        (SummaryStyle.by_topic, True),
    ],
)
async def test_generate_summary_styles_and_model_tiering(
    style: SummaryStyle, expect_strong: bool
) -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
    summaries = FakeSummaryRepo()
    if style == SummaryStyle.by_topic:
        summaries.topics = [
            TopicContextRow(
                topic_id=uuid.uuid4(),
                name="Finance",
                level=0,
                summary="Budget overview",
                parent_topic_id=None,
            )
        ]

    captured: dict[str, Any] = {}

    async def _llm(**kwargs: Any) -> StructuredLlmResult:
        captured.update(kwargs)
        return StructuredLlmResult(
            data={"summary": f"Summary for {style.value}"},
            model=kwargs["model"],
            input_tokens=12,
            output_tokens=8,
            estimated_cost_usd=0.001234,
        )

    svc = SummaryService(
        settings=_settings(),
        documents=FakeDocumentRepo(document=document, version=version),  # type: ignore[arg-type]
        retrieval=FakeRetrievalRepo(  # type: ignore[arg-type]
            chunks=[
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=version.id,
                    content="Section A discusses revenue and margins.",
                )
            ]
        ),
        summaries=summaries,  # type: ignore[arg-type]
        llm_call=_llm,
    )
    row = await svc.generate_summary(
        workspace_id=workspace_id,
        document_id=document_id,
        style=style,
        created_by=user_id,
    )
    expected_model = "claude-strong-test" if expect_strong else "claude-light-test"
    assert captured["model"] == expected_model
    assert row.type == SummaryType(style)
    assert row.source_version_id == version.id
    assert row.content == f"Summary for {style.value}"
    assert row.model_used == expected_model
    assert row.prompt_tokens == 12
    assert row.completion_tokens == 8
    assert row.cost_usd == Decimal("0.001234")
    assert row.latency_ms is not None and row.latency_ms >= 0
    assert len(summaries.created) == 1
    if style == SummaryStyle.by_topic:
        assert "Topic hierarchy" in captured["user"]
        assert "Finance" in captured["user"]


@pytest.mark.asyncio
async def test_generate_summary_truncates_to_context_window() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
    # Tiny window forces truncation of a long second chunk.
    settings = _settings(
        chat_answer_light_context_window=400,
        summary_prompt_reserve_tokens=50,
        summary_max_output_tokens=50,
    )
    long_a = "alpha " * 40
    long_b = "bravo " * 200
    captured: dict[str, Any] = {}

    async def _llm(**kwargs: Any) -> StructuredLlmResult:
        captured.update(kwargs)
        return StructuredLlmResult(
            data={"summary": "ok"},
            model=kwargs["model"],
            input_tokens=5,
            output_tokens=2,
            estimated_cost_usd=0.0,
        )

    svc = SummaryService(
        settings=settings,
        documents=FakeDocumentRepo(document=document, version=version),  # type: ignore[arg-type]
        retrieval=FakeRetrievalRepo(  # type: ignore[arg-type]
            chunks=[
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=version.id,
                    content=long_a,
                    index=0,
                ),
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=version.id,
                    content=long_b,
                    index=1,
                ),
            ]
        ),
        summaries=FakeSummaryRepo(),  # type: ignore[arg-type]
        llm_call=_llm,
    )
    row = await svc.generate_summary(
        workspace_id=workspace_id,
        document_id=document_id,
        style=SummaryStyle.short,
        created_by=user_id,
    )
    assert row.content == "ok"
    # Full second chunk should not appear; first chunk content should.
    assert "alpha" in captured["user"]
    assert long_b not in captured["user"]


@pytest.mark.asyncio
async def test_generate_summary_llm_failure_maps_domain_error() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
    svc = _service(
        docs=FakeDocumentRepo(document=document, version=version),
        retrieval=FakeRetrievalRepo(
            chunks=[
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=version.id,
                    content="hello world",
                )
            ]
        ),
        summaries=FakeSummaryRepo(),
        llm_error=RuntimeError("boom"),
    )
    with pytest.raises(SummaryServiceError) as exc:
        await svc.generate_summary(
            workspace_id=workspace_id,
            document_id=document_id,
            style=SummaryStyle.short,
            created_by=user_id,
        )
    assert exc.value.code == "llm_failed"
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_generate_summary_empty_llm_content() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
    svc = _service(
        docs=FakeDocumentRepo(document=document, version=version),
        retrieval=FakeRetrievalRepo(
            chunks=[
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=version.id,
                    content="hello world",
                )
            ]
        ),
        summaries=FakeSummaryRepo(),
        llm_result=StructuredLlmResult(
            data={"summary": "   "},
            model="claude-light-test",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        ),
    )
    with pytest.raises(SummaryServiceError) as exc:
        await svc.generate_summary(
            workspace_id=workspace_id,
            document_id=document_id,
            style=SummaryStyle.short,
            created_by=user_id,
        )
    assert exc.value.code == "empty_summary"


@pytest.mark.asyncio
async def test_summary_style_alias_is_summary_type() -> None:
    assert SummaryStyle is SummaryType
    assert SummaryStyle.short is SummaryType.short


def test_model_context_window_uses_tier_settings() -> None:
    from app.services.chat.model_tiering import model_context_window, select_answer_model

    settings = _settings(
        chat_answer_light_context_window=111,
        chat_answer_strong_context_window=222,
    )
    light = select_answer_model(settings, prefer_strong=False)
    strong = select_answer_model(settings, prefer_strong=True)
    assert model_context_window(settings, light) == 111
    assert model_context_window(settings, strong) == 222
