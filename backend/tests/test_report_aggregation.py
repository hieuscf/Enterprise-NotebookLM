# =============================================================================
# File: test_report_aggregation.py
# Module/Service: Report Service (FR9) — Data Aggregation
# Layer: Service
# Purpose: Unit tests for ReportAggregationService (mock DB / fake repos).
# Responsibilities:
#   - Workspace isolation (missing / cross-workspace → 404)
#   - order_index sort of aggregated blocks
#   - All four ReportItemInput source_type branches
# Dependencies:
#   - pytest, ReportAggregationService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres)
# Related Modules: app.services.report_aggregation
# Important Notes: Does not generate PDF/DOCX/Markdown.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.models.artifacts import Comparison, Extraction, Summary
from app.models.chat import ChatMessage, ChatSession
from app.models.documents import Document
from app.models.enums import (
    ComparisonStatus,
    ExtractionOutputFormat,
    ExtractionStatus,
    ExtractionType,
    FileType,
    MessageRole,
    ReportSourceType,
    SummaryStatus,
    SummaryType,
)
from app.repositories.comparisons import ComparisonWithDocuments
from app.services.report_aggregation import (
    AggregatedReportBlock,
    ReportAggregationError,
    ReportAggregationService,
    ReportItemInput,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeDocumentRepo:
    documents: dict[uuid.UUID, Document] = field(default_factory=dict)

    async def get_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return None
        return doc


@dataclass
class FakeSummaryRepo:
    rows: dict[uuid.UUID, Summary] = field(default_factory=dict)
    workspace_by_id: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)

    async def get(
        self, *, workspace_id: uuid.UUID, summary_id: uuid.UUID
    ) -> Summary | None:
        row = self.rows.get(summary_id)
        if row is None:
            return None
        if self.workspace_by_id.get(summary_id) != workspace_id:
            return None
        return row


@dataclass
class FakeExtractionRepo:
    rows: dict[uuid.UUID, Extraction] = field(default_factory=dict)
    workspace_by_id: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)

    async def get(
        self, *, workspace_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> Extraction | None:
        row = self.rows.get(extraction_id)
        if row is None:
            return None
        if self.workspace_by_id.get(extraction_id) != workspace_id:
            return None
        return row


@dataclass
class FakeComparisonRepo:
    rows: dict[uuid.UUID, ComparisonWithDocuments] = field(default_factory=dict)

    async def get(
        self, *, workspace_id: uuid.UUID, comparison_id: uuid.UUID
    ) -> ComparisonWithDocuments | None:
        wrapped = self.rows.get(comparison_id)
        if wrapped is None:
            return None
        if wrapped.comparison.workspace_id != workspace_id:
            return None
        return wrapped


@dataclass
class FakeChatSessionRepo:
    sessions: dict[uuid.UUID, ChatSession] = field(default_factory=dict)

    async def get(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> ChatSession | None:
        del include_deleted
        session = self.sessions.get(session_id)
        if session is None or session.workspace_id != workspace_id:
            return None
        return session


@dataclass
class FakeChatMessageRepo:
    by_session: dict[uuid.UUID, list[ChatMessage]] = field(default_factory=dict)

    async def list_for_session(self, *, session_id: uuid.UUID) -> list[ChatMessage]:
        messages = list(self.by_session.get(session_id, []))
        return sorted(messages, key=lambda m: m.created_at)


def _make_service(
    *,
    documents: FakeDocumentRepo | None = None,
    summaries: FakeSummaryRepo | None = None,
    extractions: FakeExtractionRepo | None = None,
    comparisons: FakeComparisonRepo | None = None,
    chat_sessions: FakeChatSessionRepo | None = None,
    chat_messages: FakeChatMessageRepo | None = None,
) -> ReportAggregationService:
    return ReportAggregationService(
        summaries=summaries or FakeSummaryRepo(),  # type: ignore[arg-type]
        extractions=extractions or FakeExtractionRepo(),  # type: ignore[arg-type]
        comparisons=comparisons or FakeComparisonRepo(),  # type: ignore[arg-type]
        chat_sessions=chat_sessions or FakeChatSessionRepo(),  # type: ignore[arg-type]
        chat_messages=chat_messages or FakeChatMessageRepo(),  # type: ignore[arg-type]
        documents=documents or FakeDocumentRepo(),  # type: ignore[arg-type]
    )


def _document(*, workspace_id: uuid.UUID, title: str = "Doc A") -> Document:
    return Document(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        title=title,
        file_type=FileType.pdf,
    )


def _summary(*, document_id: uuid.UUID, content: str = "summary text") -> Summary:
    return Summary(
        id=uuid.uuid4(),
        document_id=document_id,
        created_by=uuid.uuid4(),
        source_version_id=uuid.uuid4(),
        type=SummaryType.short,
        status=SummaryStatus.completed,
        content=content,
        sections=None,
    )


def _extraction(*, document_id: uuid.UUID) -> Extraction:
    return Extraction(
        id=uuid.uuid4(),
        document_id=document_id,
        created_by=uuid.uuid4(),
        source_version_id=uuid.uuid4(),
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        status=ExtractionStatus.completed,
        result_json={"rows": [{"a": 1}]},
    )


def _comparison(*, workspace_id: uuid.UUID, title: str | None = "Cmp") -> Comparison:
    return Comparison(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        created_by=uuid.uuid4(),
        title=title,
        focus=None,
        status=ComparisonStatus.completed,
        result={
            "similarities": ["same theme"],
            "differences": ["diff scope"],
        },
    )


def _session(*, workspace_id: uuid.UUID, title: str | None = "Chat") -> ChatSession:
    return ChatSession(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=uuid.uuid4(),
        title=title,
    )


def _message(
    *,
    session_id: uuid.UUID,
    role: MessageRole,
    content: str,
    created_at: datetime,
) -> ChatMessage:
    return ChatMessage(
        id=uuid.uuid4(),
        session_id=session_id,
        role=role,
        content=content,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Tests — workspace validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_raises_404_when_summary_missing() -> None:
    workspace_id = uuid.uuid4()
    service = _make_service()
    items = [
        ReportItemInput(
            source_type=ReportSourceType.summary,
            source_id=uuid.uuid4(),
            order_index=0,
        )
    ]
    with pytest.raises(ReportAggregationError) as exc_info:
        await service.aggregate(workspace_id=workspace_id, items=items)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "source_not_found"


@pytest.mark.asyncio
async def test_aggregate_rejects_cross_workspace_sources() -> None:
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    doc_b = _document(workspace_id=ws_b, title="Other WS Doc")
    summary = _summary(document_id=doc_b.id)
    extraction = _extraction(document_id=doc_b.id)
    comparison = _comparison(workspace_id=ws_b)
    session = _session(workspace_id=ws_b)

    summaries = FakeSummaryRepo(
        rows={summary.id: summary},
        workspace_by_id={summary.id: ws_b},
    )
    extractions = FakeExtractionRepo(
        rows={extraction.id: extraction},
        workspace_by_id={extraction.id: ws_b},
    )
    comparisons = FakeComparisonRepo(
        rows={
            comparison.id: ComparisonWithDocuments(
                comparison=comparison, document_ids=[]
            )
        }
    )
    chat_sessions = FakeChatSessionRepo(sessions={session.id: session})
    service = _make_service(
        summaries=summaries,
        extractions=extractions,
        comparisons=comparisons,
        chat_sessions=chat_sessions,
    )

    for source_type, source_id in (
        (ReportSourceType.summary, summary.id),
        (ReportSourceType.extraction, extraction.id),
        (ReportSourceType.comparison, comparison.id),
        (ReportSourceType.chat_session, session.id),
    ):
        with pytest.raises(ReportAggregationError) as exc_info:
            await service.aggregate(
                workspace_id=ws_a,
                items=[
                    ReportItemInput(
                        source_type=source_type,
                        source_id=source_id,
                        order_index=0,
                    )
                ],
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "source_not_found"


# ---------------------------------------------------------------------------
# Tests — order_index sort
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_sorts_by_order_index() -> None:
    workspace_id = uuid.uuid4()
    doc = _document(workspace_id=workspace_id, title="Alpha")
    summary = _summary(document_id=doc.id, content="S")
    extraction = _extraction(document_id=doc.id)
    comparison = _comparison(workspace_id=workspace_id, title="Cmp title")
    session = _session(workspace_id=workspace_id, title="Session title")

    service = _make_service(
        documents=FakeDocumentRepo(documents={doc.id: doc}),
        summaries=FakeSummaryRepo(
            rows={summary.id: summary},
            workspace_by_id={summary.id: workspace_id},
        ),
        extractions=FakeExtractionRepo(
            rows={extraction.id: extraction},
            workspace_by_id={extraction.id: workspace_id},
        ),
        comparisons=FakeComparisonRepo(
            rows={
                comparison.id: ComparisonWithDocuments(
                    comparison=comparison, document_ids=[]
                )
            }
        ),
        chat_sessions=FakeChatSessionRepo(sessions={session.id: session}),
        chat_messages=FakeChatMessageRepo(by_session={session.id: []}),
    )

    items = [
        ReportItemInput(
            source_type=ReportSourceType.chat_session,
            source_id=session.id,
            order_index=3,
        ),
        ReportItemInput(
            source_type=ReportSourceType.summary,
            source_id=summary.id,
            order_index=0,
        ),
        ReportItemInput(
            source_type=ReportSourceType.comparison,
            source_id=comparison.id,
            order_index=2,
        ),
        ReportItemInput(
            source_type=ReportSourceType.extraction,
            source_id=extraction.id,
            order_index=1,
        ),
    ]

    blocks = await service.aggregate(workspace_id=workspace_id, items=items)
    assert [b.order_index for b in blocks] == [0, 1, 2, 3]
    assert [b.source_type for b in blocks] == [
        ReportSourceType.summary,
        ReportSourceType.extraction,
        ReportSourceType.comparison,
        ReportSourceType.chat_session,
    ]


# ---------------------------------------------------------------------------
# Tests — four source types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_summary_block() -> None:
    workspace_id = uuid.uuid4()
    doc = _document(workspace_id=workspace_id, title="Policy")
    summary = _summary(document_id=doc.id, content="Short blurb")
    service = _make_service(
        documents=FakeDocumentRepo(documents={doc.id: doc}),
        summaries=FakeSummaryRepo(
            rows={summary.id: summary},
            workspace_by_id={summary.id: workspace_id},
        ),
    )
    blocks = await service.aggregate(
        workspace_id=workspace_id,
        items=[
            ReportItemInput(
                source_type=ReportSourceType.summary,
                source_id=summary.id,
                order_index=1,
            )
        ],
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert isinstance(block, AggregatedReportBlock)
    assert block.source_type is ReportSourceType.summary
    assert block.order_index == 1
    assert "short" in block.title.lower()
    assert "Policy" in block.title
    assert block.content["text"] == "Short blurb"
    assert block.content["style"] == "short"


@pytest.mark.asyncio
async def test_aggregate_extraction_block() -> None:
    workspace_id = uuid.uuid4()
    doc = _document(workspace_id=workspace_id, title="Tables Doc")
    extraction = _extraction(document_id=doc.id)
    service = _make_service(
        documents=FakeDocumentRepo(documents={doc.id: doc}),
        extractions=FakeExtractionRepo(
            rows={extraction.id: extraction},
            workspace_by_id={extraction.id: workspace_id},
        ),
    )
    blocks = await service.aggregate(
        workspace_id=workspace_id,
        items=[
            ReportItemInput(
                source_type=ReportSourceType.extraction,
                source_id=extraction.id,
                order_index=0,
            )
        ],
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert block.source_type is ReportSourceType.extraction
    assert block.content["extraction_type"] == "table"
    assert block.content["result"] == {"rows": [{"a": 1}]}
    assert "Tables Doc" in block.title


@pytest.mark.asyncio
async def test_aggregate_comparison_block() -> None:
    workspace_id = uuid.uuid4()
    comparison = _comparison(workspace_id=workspace_id, title="Q1 vs Q2")
    service = _make_service(
        comparisons=FakeComparisonRepo(
            rows={
                comparison.id: ComparisonWithDocuments(
                    comparison=comparison, document_ids=[]
                )
            }
        )
    )
    blocks = await service.aggregate(
        workspace_id=workspace_id,
        items=[
            ReportItemInput(
                source_type=ReportSourceType.comparison,
                source_id=comparison.id,
                order_index=5,
            )
        ],
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert block.source_type is ReportSourceType.comparison
    assert block.title == "Q1 vs Q2"
    assert block.content["similarities"] == ["same theme"]
    assert block.content["differences"] == ["diff scope"]


@pytest.mark.asyncio
async def test_aggregate_chat_session_block_sorted_by_time() -> None:
    workspace_id = uuid.uuid4()
    session = _session(workspace_id=workspace_id, title="Research chat")
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 10, 5, tzinfo=UTC)
    messages = [
        _message(
            session_id=session.id,
            role=MessageRole.assistant,
            content="Answer",
            created_at=t1,
        ),
        _message(
            session_id=session.id,
            role=MessageRole.user,
            content="Question",
            created_at=t0,
        ),
    ]
    service = _make_service(
        chat_sessions=FakeChatSessionRepo(sessions={session.id: session}),
        chat_messages=FakeChatMessageRepo(by_session={session.id: messages}),
    )
    blocks = await service.aggregate(
        workspace_id=workspace_id,
        items=[
            ReportItemInput(
                source_type=ReportSourceType.chat_session,
                source_id=session.id,
                order_index=0,
            )
        ],
    )
    assert len(blocks) == 1
    block = blocks[0]
    assert block.source_type is ReportSourceType.chat_session
    assert block.title == "Research chat"
    assert [m["role"] for m in block.content["messages"]] == ["user", "assistant"]
    assert [m["content"] for m in block.content["messages"]] == ["Question", "Answer"]
    assert block.content["messages"][0]["created_at"] == t0.isoformat()


@pytest.mark.asyncio
async def test_aggregate_empty_items_returns_empty_list() -> None:
    service = _make_service()
    blocks = await service.aggregate(workspace_id=uuid.uuid4(), items=[])
    assert blocks == []


@pytest.mark.asyncio
async def test_aggregate_invalid_source_type_raises_400() -> None:
    service = _make_service()
    items = [
        ReportItemInput(
            source_type="bogus",  # type: ignore[arg-type]
            source_id=uuid.uuid4(),
            order_index=0,
        )
    ]
    with pytest.raises(ReportAggregationError) as exc_info:
        await service.aggregate(workspace_id=uuid.uuid4(), items=items)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_source_type"
