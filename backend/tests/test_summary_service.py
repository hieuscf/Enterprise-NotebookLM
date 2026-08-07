# =============================================================================
# File: test_summary_service.py
# Module/Service: Summary Service (FR6 Part 1+2)
# Layer: Service
# Purpose: Unit tests for request/process/generate_summary branches.
# Responsibilities:
#   - Cover not-found / no-version / not-ready / no-chunks / llm missing
#   - Cover all four styles + by_topic; model tiering; context truncation
#   - Cover process_summary idempotency + source_version pinning
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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.adapters.llm_result import StructuredLlmResult
from app.core.config import Settings
from app.models.artifacts import Summary
from app.models.documents import Document, DocumentVersion
from app.models.enums import (
    DocumentVersionStatus,
    FileType,
    SummaryStatus,
    SummaryStyle,
    SummaryType,
)
from app.repositories.retrieval import ChunkHydrationRow
from app.repositories.summaries import TopicContextRow
from app.services.summary.summary_service import SummaryService, SummaryServiceError


@dataclass
class FakeSession:
    commits: int = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        return None


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
    chunks: list[ChunkHydrationRow] | None = None

    async def list_chunks_for_document(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
    ) -> list[ChunkHydrationRow]:
        del workspace_id, document_id
        if version_id is not None and version_id in self.chunks_by_version:
            return list(self.chunks_by_version[version_id])
        return list(self.chunks or [])


class FakeSummaryRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Summary] = {}
        self.topics: list[TopicContextRow] = []

    async def create_processing(self, **kwargs: Any) -> Summary:
        row = Summary(
            id=uuid.uuid4(),
            document_id=kwargs["document_id"],
            created_by=kwargs["created_by"],
            source_version_id=kwargs["source_version_id"],
            type=kwargs["type_"],
            status=SummaryStatus.processing,
            content=None,
            model_used=None,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=None,
            created_at=datetime.now(UTC),
        )
        self.rows[row.id] = row
        return row

    async def get_by_id(self, summary_id: uuid.UUID) -> Summary | None:
        return self.rows.get(summary_id)

    async def get(
        self, *, workspace_id: uuid.UUID, summary_id: uuid.UUID
    ) -> Summary | None:
        del workspace_id
        return self.rows.get(summary_id)

    async def list_for_document(
        self, *, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[Summary]:
        del workspace_id
        items = [r for r in self.rows.values() if r.document_id == document_id]
        return sorted(items, key=lambda r: r.created_at, reverse=True)

    async def update_generation_result(self, *, summary_id: uuid.UUID, **kwargs: Any) -> bool:
        row = self.rows.get(summary_id)
        if row is None or row.status != SummaryStatus.processing:
            return False
        row.content = kwargs["content"]
        row.sections = kwargs.get("sections")
        row.model_used = kwargs["model_used"]
        row.prompt_tokens = kwargs["prompt_tokens"]
        row.completion_tokens = kwargs["completion_tokens"]
        row.cost_usd = kwargs["cost_usd"]
        row.latency_ms = kwargs["latency_ms"]
        row.status = SummaryStatus.completed
        return True

    async def mark_failed(self, *, summary_id: uuid.UUID) -> bool:
        row = self.rows.get(summary_id)
        if row is None or row.status != SummaryStatus.processing:
            return False
        row.status = SummaryStatus.failed
        row.content = None
        return True

    async def delete(self, summary: Summary) -> None:
        self.rows.pop(summary.id, None)

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
    enqueue: bool = False,
    enqueue_fn: Any | None = None,
    session: FakeSession | None = None,
) -> SummaryService:
    async def _llm(**kwargs: Any) -> StructuredLlmResult:
        del kwargs
        if llm_error is not None:
            raise llm_error
        assert llm_result is not None
        return llm_result

    return SummaryService(
        settings=settings or _settings(),
        session=session or FakeSession(),  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        retrieval=retrieval,  # type: ignore[arg-type]
        summaries=summaries,  # type: ignore[arg-type]
        llm_call=_llm if (llm_result is not None or llm_error is not None) else None,
        enqueue=enqueue,
        enqueue_fn=enqueue_fn,
    )


@pytest.mark.asyncio
async def test_generate_summary_document_not_found() -> None:
    svc = _service(
        docs=FakeDocumentRepo(),
        retrieval=FakeRetrievalRepo(),
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
            workspace_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            style=SummaryStyle.short,
            created_by=uuid.uuid4(),
        )
    assert exc.value.code == "not_found"


@pytest.mark.asyncio
async def test_generate_summary_no_current_version() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle(with_current=False)
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
    assert exc.value.code == "no_current_version"


@pytest.mark.asyncio
async def test_generate_summary_version_not_ready() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle(
        status=DocumentVersionStatus.processing
    )
    svc = _service(
        docs=FakeDocumentRepo(document=document, version=version),
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
    assert exc.value.code == "llm_failed"


@pytest.mark.asyncio
async def test_generate_summary_llm_not_configured() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
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
        settings=_settings(anthropic_api_key=None),
    )
    with pytest.raises(SummaryServiceError) as exc:
        await svc.generate_summary(
            workspace_id=workspace_id,
            document_id=document_id,
            style=SummaryStyle.short,
            created_by=user_id,
        )
    assert exc.value.code == "llm_failed"


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
        data: dict[str, Any] = {"summary": f"Summary for {style.value}"}
        if style == SummaryStyle.by_topic:
            data = {
                "summary": f"Summary for {style.value}",
                "sections": [
                    {
                        "topic_id": str(summaries.topics[0].topic_id),
                        "title": "Finance",
                        "content": "Budget overview details.",
                    }
                ],
            }
        return StructuredLlmResult(
            data=data,
            model=kwargs["model"],
            input_tokens=12,
            output_tokens=8,
            estimated_cost_usd=0.001234,
        )

    svc = SummaryService(
        settings=_settings(),
        session=FakeSession(),  # type: ignore[arg-type]
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
        enqueue=False,
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
    assert row.status == SummaryStatus.completed
    assert row.source_version_id == version.id
    assert row.content == f"Summary for {style.value}"
    assert row.model_used == expected_model
    assert row.prompt_tokens == 12
    assert row.completion_tokens == 8
    assert row.cost_usd == Decimal("0.001234")
    assert len(summaries.rows) == 1
    if style == SummaryStyle.by_topic:
        assert "Topic hierarchy" in captured["user"]
        assert "Finance" in captured["user"]
        assert row.sections is not None
        assert row.sections[0]["title"] == "Finance"


@pytest.mark.asyncio
async def test_request_summary_enqueues_without_llm() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
    session = FakeSession()
    enqueued: list[uuid.UUID] = []
    llm_called = False

    async def _llm(**kwargs: Any) -> StructuredLlmResult:
        nonlocal llm_called
        llm_called = True
        del kwargs
        return StructuredLlmResult(
            data={"summary": "x"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        )

    svc = SummaryService(
        settings=_settings(),
        session=session,  # type: ignore[arg-type]
        documents=FakeDocumentRepo(document=document, version=version),  # type: ignore[arg-type]
        retrieval=FakeRetrievalRepo(chunks=[]),  # type: ignore[arg-type]
        summaries=FakeSummaryRepo(),  # type: ignore[arg-type]
        llm_call=_llm,
        enqueue=True,
        enqueue_fn=lambda sid: enqueued.append(sid),
    )
    row = await svc.request_summary(
        workspace_id=workspace_id,
        document_id=document_id,
        style=SummaryStyle.short,
        created_by=user_id,
    )
    assert row.status == SummaryStatus.processing
    assert row.content is None
    assert row.source_version_id == version.id
    assert session.commits >= 1
    assert enqueued == [row.id]
    assert llm_called is False


@pytest.mark.asyncio
async def test_process_summary_uses_pinned_source_version() -> None:
    workspace_id, document_id, user_id, document, v2 = _doc_bundle()
    v3_id = uuid.uuid4()
    v3 = DocumentVersion(
        id=v3_id,
        document_id=document_id,
        uploaded_by=user_id,
        version_number=3,
        storage_path="workspaces/x/documents/y/v3/a.pdf",
        file_size_bytes=10,
        checksum_sha256="b" * 64,
        status=DocumentVersionStatus.ready,
        is_current=True,
    )
    # After POST, current flips to V3 — worker must still use V2.
    document.current_version_id = v3_id
    docs = FakeDocumentRepo(
        document=document,
        version=v3,
        versions={v2.id: v2, v3_id: v3},
    )
    retrieval = FakeRetrievalRepo(
        chunks_by_version={
            v2.id: [
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=v2.id,
                    content="VERSION TWO CONTENT",
                )
            ],
            v3_id: [
                _chunk(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    version_id=v3_id,
                    content="VERSION THREE CONTENT",
                )
            ],
        }
    )
    summaries = FakeSummaryRepo()
    row = await summaries.create_processing(
        document_id=document_id,
        created_by=user_id,
        source_version_id=v2.id,
        type_=SummaryType.short,
    )
    captured: dict[str, Any] = {}

    async def _llm(**kwargs: Any) -> StructuredLlmResult:
        captured.update(kwargs)
        return StructuredLlmResult(
            data={"summary": "from-v2"},
            model="claude-light-test",
            input_tokens=3,
            output_tokens=2,
            estimated_cost_usd=0.01,
        )

    svc = SummaryService(
        settings=_settings(),
        session=FakeSession(),  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        retrieval=retrieval,  # type: ignore[arg-type]
        summaries=summaries,  # type: ignore[arg-type]
        llm_call=_llm,
        enqueue=False,
    )
    final = await svc.process_summary(row.id)
    assert final is not None
    assert final.status == SummaryStatus.completed
    assert final.source_version_id == v2.id
    assert final.content == "from-v2"
    assert "VERSION TWO CONTENT" in captured["user"]
    assert "VERSION THREE CONTENT" not in captured["user"]


@pytest.mark.asyncio
async def test_process_summary_missing_and_idempotent() -> None:
    summaries = FakeSummaryRepo()
    svc = _service(
        docs=FakeDocumentRepo(),
        retrieval=FakeRetrievalRepo(),
        summaries=summaries,
        llm_result=StructuredLlmResult(
            data={"summary": "x"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        ),
    )
    assert await svc.process_summary(uuid.uuid4()) is None

    workspace_id, document_id, user_id, document, version = _doc_bundle()
    row = await summaries.create_processing(
        document_id=document_id,
        created_by=user_id,
        source_version_id=version.id,
        type_=SummaryType.short,
    )
    row.status = SummaryStatus.completed
    row.content = "already done"
    docs = FakeDocumentRepo(document=document, version=version)
    svc2 = _service(
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
        summaries=summaries,
        llm_result=StructuredLlmResult(
            data={"summary": "new"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        ),
    )
    out = await svc2.process_summary(row.id)
    assert out is not None
    assert out.content == "already done"


@pytest.mark.asyncio
async def test_process_summary_failure_marks_failed() -> None:
    workspace_id, document_id, user_id, document, version = _doc_bundle()
    summaries = FakeSummaryRepo()
    row = await summaries.create_processing(
        document_id=document_id,
        created_by=user_id,
        source_version_id=version.id,
        type_=SummaryType.short,
    )
    svc = _service(
        docs=FakeDocumentRepo(document=document, version=version),
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
        summaries=summaries,
        llm_error=RuntimeError("boom"),
    )
    final = await svc.process_summary(row.id)
    assert final is not None
    assert final.status == SummaryStatus.failed
    assert final.content is None
    assert final.source_version_id == version.id


@pytest.mark.asyncio
async def test_process_deleted_summary_not_recreated() -> None:
    summaries = FakeSummaryRepo()
    missing_id = uuid.uuid4()
    svc = _service(
        docs=FakeDocumentRepo(),
        retrieval=FakeRetrievalRepo(),
        summaries=summaries,
        llm_result=StructuredLlmResult(
            data={"summary": "x"},
            model="m",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.0,
        ),
    )
    assert await svc.process_summary(missing_id) is None
    assert summaries.rows == {}


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
