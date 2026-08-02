# =============================================================================
# File: test_metadata_factoid_handlers.py
# Module/Service: Query Router — Metadata / Factoid Handlers (FR11 / Task 3)
# Layer: Service
# Purpose: Unit tests for 0-LLM metadata + factoid handlers and unified result.
# Responsibilities:
#   - Metadata whitelist intents; factoid confidence/extractive/downgrade
#   - Ensure no LLM / no paraphrase; QueryRouterResult shape
# Dependencies:
#   - pytest, app.services.query_router.handlers.*
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: MetadataHandler, FactoidHandler, QueryRouterResult
# Important Notes: 0 LLM; fakes only.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import FileType, RouteType
from app.services.query_router.handlers.factoid_handler import FactoidHandler
from app.services.query_router.handlers.metadata_handler import MetadataHandler
from app.services.query_router.interfaces.metadata_repository import MetadataDocumentInfo
from app.services.query_router.interfaces.retriever import RetrievedChunk
from app.services.query_router.metadata_registry import MetadataRegistry
from app.services.query_router.response_models import QueryRouterResult
from app.services.query_router.templates import render_template


class FakeMetadataRepo:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.count = 234
        self.docs = [
            MetadataDocumentInfo(
                document_id=uuid.uuid4(),
                title="Policy.pdf",
                file_type="pdf",
                created_at=datetime.now(UTC),
                uploaded_by=uuid.uuid4(),
            ),
            MetadataDocumentInfo(
                document_id=uuid.uuid4(),
                title="Guide.docx",
                file_type="docx",
                created_at=datetime.now(UTC),
                uploaded_by=uuid.uuid4(),
            ),
        ]

    async def count_documents(
        self, workspace_id: uuid.UUID, *, file_type: FileType | None = None
    ) -> int:
        self.calls.append(f"count_documents:{file_type}")
        return self.count if file_type is None else 12

    async def count_files(
        self, workspace_id: uuid.UUID, *, file_type: FileType | None = None
    ) -> int:
        self.calls.append("count_files")
        return await self.count_documents(workspace_id, file_type=file_type)

    async def count_pdf(self, workspace_id: uuid.UUID) -> int:
        self.calls.append("count_pdf")
        return 12

    async def list_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
        limit: int = 50,
    ) -> list[MetadataDocumentInfo]:
        self.calls.append(f"list_documents:{file_type}")
        rows = self.docs
        if file_type is not None:
            rows = [d for d in rows if d.file_type == file_type.value]
        return rows[:limit]

    async def latest_documents(
        self, workspace_id: uuid.UUID, *, limit: int = 10
    ) -> list[MetadataDocumentInfo]:
        self.calls.append("latest_documents")
        return self.docs[:limit]

    async def oldest_documents(
        self, workspace_id: uuid.UUID, *, limit: int = 10
    ) -> list[MetadataDocumentInfo]:
        self.calls.append("oldest_documents")
        return list(reversed(self.docs))[:limit]

    async def count_chunks(self, workspace_id: uuid.UUID) -> int:
        self.calls.append("count_chunks")
        return 100

    async def count_pages(self, workspace_id: uuid.UUID) -> int:
        self.calls.append("count_pages")
        return 50

    async def count_members(self, workspace_id: uuid.UUID) -> int:
        self.calls.append("count_members")
        return 4

    async def stats_by_file_type(self, workspace_id: uuid.UUID) -> dict[str, int]:
        self.calls.append("stats_by_file_type")
        return {"pdf": 3, "docx": 2}

    async def document_owner(
        self, workspace_id: uuid.UUID, *, document_id: uuid.UUID | None = None
    ) -> MetadataDocumentInfo | None:
        self.calls.append("document_owner")
        return self.docs[0]


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.calls = 0
        self.last_top_k: int | None = None

    async def retrieve(
        self, query: str, top_k: int, *, workspace_id: uuid.UUID
    ) -> list[RetrievedChunk]:
        self.calls += 1
        self.last_top_k = top_k
        return self.chunks[:top_k]


WS = uuid.uuid4()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metadata_count_documents_calls_repo_and_template() -> None:
    repo = FakeMetadataRepo()
    handler = MetadataHandler(repository=repo)  # type: ignore[arg-type]
    result = await handler.handle(workspace_id=WS, query_text="Có bao nhiêu tài liệu?")
    assert result.route_type == RouteType.metadata
    assert result.answer == render_template("count_documents_vi", count=234)
    assert "count_documents" in repo.calls[0]
    assert result.confidence == 1.0
    assert isinstance(result, QueryRouterResult)


@pytest.mark.asyncio
async def test_metadata_list_documents() -> None:
    repo = FakeMetadataRepo()
    handler = MetadataHandler(repository=repo)  # type: ignore[arg-type]
    result = await handler.handle(workspace_id=WS, query_text="Danh sách tài liệu")
    assert result.route_type == RouteType.metadata
    assert "Policy.pdf" in (result.answer or "")
    assert any(c.startswith("list_documents") for c in repo.calls)


@pytest.mark.asyncio
async def test_metadata_latest_documents() -> None:
    repo = FakeMetadataRepo()
    handler = MetadataHandler(repository=repo)  # type: ignore[arg-type]
    result = await handler.handle(workspace_id=WS, query_text="Latest documents")
    assert result.route_type == RouteType.metadata
    assert "latest_documents" in repo.calls
    assert result.answer is not None


@pytest.mark.asyncio
async def test_metadata_uploaded_by() -> None:
    repo = FakeMetadataRepo()
    handler = MetadataHandler(repository=repo)  # type: ignore[arg-type]
    result = await handler.handle(workspace_id=WS, query_text="Who uploaded this file?")
    assert result.route_type == RouteType.metadata
    assert "document_owner" in repo.calls
    assert str(repo.docs[0].uploaded_by) in (result.answer or "")


@pytest.mark.asyncio
async def test_metadata_unsupported_downgrades_to_complex() -> None:
    repo = FakeMetadataRepo()
    handler = MetadataHandler(repository=repo)  # type: ignore[arg-type]
    result = await handler.handle(workspace_id=WS, query_text="Thống kê tag trong workspace")
    assert result.route_type == RouteType.complex
    assert result.answer is None
    assert repo.calls == []


@pytest.mark.asyncio
async def test_metadata_never_calls_llm_or_retrieval() -> None:
    repo = FakeMetadataRepo()
    handler = MetadataHandler(repository=repo)  # type: ignore[arg-type]
    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        autospec=True,
    ) as llm:
        await handler.handle(workspace_id=WS, query_text="How many documents?")
        llm.assert_not_called()


# ---------------------------------------------------------------------------
# Factoid
# ---------------------------------------------------------------------------


def _chunk(score: float, text: str = "Warranty period: 24 months.") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        text=text,
        score=score,
        page_number=3,
        char_start=0,
        char_end=len(text),
    )


@pytest.mark.asyncio
async def test_factoid_top1_confidence_ok_extractive() -> None:
    chunk = _chunk(0.92)
    retriever = FakeRetriever([chunk])
    handler = FactoidHandler(
        retriever=retriever,  # type: ignore[arg-type]
        confidence_threshold=0.75,
        top_k=1,
    )
    result = await handler.handle(workspace_id=WS, query_text="What is warranty period?")
    assert result.route_type == RouteType.factoid
    assert result.answer == "Warranty period: 24 months."
    assert result.confidence == pytest.approx(0.92)
    assert result.citation_refs[0].chunk_id == chunk.chunk_id
    assert result.citation_refs[0].page_number == 3
    assert retriever.last_top_k == 1
    assert isinstance(result, QueryRouterResult)


@pytest.mark.asyncio
async def test_factoid_top3_picks_best_score() -> None:
    chunks = [_chunk(0.40, "low"), _chunk(0.88, "best text"), _chunk(0.50, "mid")]
    retriever = FakeRetriever(chunks)
    handler = FactoidHandler(
        retriever=retriever,  # type: ignore[arg-type]
        confidence_threshold=0.75,
        top_k=3,
    )
    result = await handler.handle(workspace_id=WS, query_text="q")
    assert result.route_type == RouteType.factoid
    assert result.answer == "best text"
    assert retriever.last_top_k == 3


@pytest.mark.asyncio
async def test_factoid_low_confidence_downgrades() -> None:
    retriever = FakeRetriever([_chunk(0.40)])
    handler = FactoidHandler(
        retriever=retriever,  # type: ignore[arg-type]
        confidence_threshold=0.75,
        top_k=1,
    )
    result = await handler.handle(workspace_id=WS, query_text="q")
    assert result.route_type == RouteType.complex
    assert result.answer is None
    assert "confidence_below_threshold" in str(result.metadata.get("fallback_reason"))


@pytest.mark.asyncio
async def test_factoid_no_chunks_downgrades() -> None:
    retriever = FakeRetriever([])
    handler = FactoidHandler(
        retriever=retriever,  # type: ignore[arg-type]
        confidence_threshold=0.75,
        top_k=1,
    )
    result = await handler.handle(workspace_id=WS, query_text="q")
    assert result.route_type == RouteType.complex
    assert result.metadata.get("fallback_reason") == "no_retrieval_hits"


@pytest.mark.asyncio
async def test_factoid_does_not_paraphrase() -> None:
    raw = "Contract signed by Alice on 2024-01-01."
    retriever = FakeRetriever([_chunk(0.99, raw)])
    handler = FactoidHandler(
        retriever=retriever,  # type: ignore[arg-type]
        confidence_threshold=0.5,
        top_k=1,
    )
    result = await handler.handle(workspace_id=WS, query_text="Who signed?")
    assert result.answer == raw
    assert "The contract" not in (result.answer or "")


@pytest.mark.asyncio
async def test_factoid_never_calls_llm() -> None:
    retriever = FakeRetriever([_chunk(0.9)])
    handler = FactoidHandler(
        retriever=retriever,  # type: ignore[arg-type]
        confidence_threshold=0.5,
        top_k=1,
    )
    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        autospec=True,
    ) as llm:
        await handler.handle(workspace_id=WS, query_text="q")
        llm.assert_not_called()


def test_registry_match_and_template_keys() -> None:
    reg = MetadataRegistry()
    assert reg.match("Count invoices") is not None or reg.match("How many documents") is not None
    assert render_template("count_documents_en", count=1) == (
        "Workspace currently contains 1 documents."
    )
