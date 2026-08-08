# =============================================================================
# File: test_comparison_service.py
# Module/Service: Comparison Service (FR8 Prompt 1/3)
# Layer: Service
# Purpose: Unit tests for comparison prompt builder, JSON parser, and mocked LLM path.
# Responsibilities:
#   - Cover focus vs non-focus prompt constraints
#   - Cover parse_comparison_result (valid / fenced / invalid payloads)
#   - Cover create_comparison with injected LLM (no real provider call)
# Dependencies:
#   - pytest, ComparisonService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres)
# Related Modules: app.services.comparison
# Important Notes: LLM is injected; does not call Anthropic/OpenAI.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.adapters.llm_result import StructuredLlmResult
from app.core.config import Settings
from app.models.artifacts import Comparison, Summary
from app.models.documents import Document, DocumentVersion
from app.models.enums import (
    DocumentVersionStatus,
    FileType,
    SummaryStatus,
    SummaryType,
)
from app.repositories.comparisons import ComparisonWithDocuments
from app.repositories.retrieval import ChunkHydrationRow
from app.services.comparison.comparison_service import (
    ComparisonService,
    ComparisonServiceError,
)
from app.services.comparison.prompts import (
    DocumentCompareContext,
    build_comparison_prompts,
)
from app.services.comparison.result_schemas import (
    ComparisonResult,
    comparison_result_to_dict,
    parse_comparison_result,
)

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _chunk(
    *,
    content: str,
    document_id: uuid.UUID | None = None,
    index: int = 0,
) -> ChunkHydrationRow:
    doc_id = document_id or uuid.uuid4()
    return ChunkHydrationRow(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_version_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        content=content,
        title="Doc",
        chunk_index=index,
        heading_path=f"Section {index}",
    )


def test_build_comparison_prompts_without_focus_includes_documents() -> None:
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    contexts = [
        DocumentCompareContext(
            document_id=str(doc_a),
            title="Policy A",
            source="summary",
            summary_text="Both cover remote work eligibility.",
        ),
        DocumentCompareContext(
            document_id=str(doc_b),
            title="Policy B",
            source="chunks",
            chunks=[_chunk(content="Remote work requires manager approval.", document_id=doc_b)],
        ),
    ]

    system, user = build_comparison_prompts(documents=contexts, focus=None)

    assert "similarities" in system
    assert "differences" in system
    assert "Do not invent" in system
    assert "Focus constraint" not in system
    assert "Policy A" in user
    assert "Policy B" in user
    assert str(doc_a) in user
    assert "completed summary" in user
    assert "topic-ranked excerpts" in user
    assert "Comparison focus:" not in user


def test_build_comparison_prompts_with_focus_constrains_system_and_user() -> None:
    contexts = [
        DocumentCompareContext(
            document_id=str(uuid.uuid4()),
            title="Doc 1",
            source="summary",
            summary_text="Budget FY24 overview.",
        ),
        DocumentCompareContext(
            document_id=str(uuid.uuid4()),
            title="Doc 2",
            source="summary",
            summary_text="Budget FY25 overview.",
        ),
    ]

    system, user = build_comparison_prompts(documents=contexts, focus="  budget  ")

    assert 'Focus constraint: Limit the comparison to the topic "budget"' in system
    assert "Comparison focus: budget" in user
    assert "empty arrays rather than inventing" in system


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------


def test_parse_comparison_result_from_dict_strips_empty_strings() -> None:
    parsed = parse_comparison_result(
        {
            "similarities": ["  Both mention SLA  ", "", "Shared vendor list"],
            "differences": ["Doc A has penalties", "   "],
        }
    )
    assert parsed.similarities == ["Both mention SLA", "Shared vendor list"]
    assert parsed.differences == ["Doc A has penalties"]
    assert comparison_result_to_dict(parsed) == {
        "similarities": ["Both mention SLA", "Shared vendor list"],
        "differences": ["Doc A has penalties"],
    }


def test_parse_comparison_result_from_fenced_json_text() -> None:
    raw = """```json
{
  "similarities": ["Same scope"],
  "differences": ["Different owners"]
}
```"""
    parsed = parse_comparison_result(raw)
    assert parsed == ComparisonResult(
        similarities=["Same scope"],
        differences=["Different owners"],
    )


def test_parse_comparison_result_allows_empty_arrays() -> None:
    parsed = parse_comparison_result({"similarities": [], "differences": []})
    assert parsed.similarities == []
    assert parsed.differences == []


def test_parse_comparison_result_rejects_non_string_items() -> None:
    with pytest.raises((ValidationError, ValueError)):
        parse_comparison_result({"similarities": [1], "differences": []})


def test_parse_comparison_result_rejects_extra_keys() -> None:
    with pytest.raises(ValidationError):
        parse_comparison_result(
            {
                "similarities": [],
                "differences": [],
                "recommendation": "pick A",
            }
        )


def test_parse_comparison_result_rejects_non_object_json() -> None:
    with pytest.raises(ValueError):
        parse_comparison_result("[1, 2, 3]")


# ---------------------------------------------------------------------------
# Service (mocked LLM)
# ---------------------------------------------------------------------------


@dataclass
class FakeSession:
    commits: int = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        return None


@dataclass
class FakeDocumentRepo:
    documents: dict[uuid.UUID, Document] = field(default_factory=dict)
    versions: dict[uuid.UUID, DocumentVersion] = field(default_factory=dict)

    async def get_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return None
        return doc

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return None
        ver = self.versions.get(version_id)
        if ver is None or ver.document_id != document_id:
            return None
        return ver


@dataclass
class FakeRetrievalRepo:
    chunks_by_version: dict[uuid.UUID, list[ChunkHydrationRow]] = field(default_factory=dict)
    last_focus: str | None = None

    async def list_top_chunks_by_topic(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID,
        focus: str | None = None,
        limit: int = 8,
    ) -> list[ChunkHydrationRow]:
        del workspace_id, document_id
        self.last_focus = focus
        chunks = list(self.chunks_by_version.get(version_id, []))
        return chunks[:limit]


@dataclass
class FakeSummaryRepo:
    by_version: dict[uuid.UUID, Summary] = field(default_factory=dict)

    async def get_latest_completed_for_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        source_version_id: uuid.UUID,
    ) -> Summary | None:
        del workspace_id, document_id
        return self.by_version.get(source_version_id)


class FakeComparisonRepo:
    def __init__(self) -> None:
        self.created: list[ComparisonWithDocuments] = []

    async def create(self, **kwargs: Any) -> ComparisonWithDocuments:
        row = Comparison(
            id=uuid.uuid4(),
            workspace_id=kwargs["workspace_id"],
            created_by=kwargs["created_by"],
            title=kwargs.get("title"),
            result=kwargs["result"],
            created_at=datetime.now(UTC),
        )
        outcome = ComparisonWithDocuments(
            comparison=row,
            document_ids=list(kwargs["document_ids"]),
        )
        self.created.append(outcome)
        return outcome

    async def list_for_workspace(self, *, workspace_id: uuid.UUID) -> list[ComparisonWithDocuments]:
        return [c for c in self.created if c.comparison.workspace_id == workspace_id]

    async def get(
        self, *, workspace_id: uuid.UUID, comparison_id: uuid.UUID
    ) -> ComparisonWithDocuments | None:
        for item in self.created:
            if (
                item.comparison.id == comparison_id
                and item.comparison.workspace_id == workspace_id
            ):
                return item
        return None

    async def delete(self, comparison: Comparison) -> None:
        self.created = [c for c in self.created if c.comparison.id != comparison.id]


def _ready_doc(
    *,
    workspace_id: uuid.UUID,
    title: str,
) -> tuple[Document, DocumentVersion]:
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    user_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        workspace_id=workspace_id,
        title=title,
        file_type=FileType.pdf,
        current_version_id=ver_id,
    )
    ver = DocumentVersion(
        id=ver_id,
        document_id=doc_id,
        uploaded_by=user_id,
        version_number=1,
        storage_path=f"workspaces/{workspace_id}/documents/{doc_id}/v1/a.pdf",
        file_size_bytes=10,
        checksum_sha256="a" * 64,
        status=DocumentVersionStatus.ready,
        is_current=True,
    )
    return doc, ver


@pytest.mark.asyncio
async def test_create_comparison_uses_summary_context_and_strong_model() -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    doc_a, ver_a = _ready_doc(workspace_id=workspace_id, title="Alpha")
    doc_b, ver_b = _ready_doc(workspace_id=workspace_id, title="Beta")

    documents = FakeDocumentRepo(
        documents={doc_a.id: doc_a, doc_b.id: doc_b},
        versions={ver_a.id: ver_a, ver_b.id: ver_b},
    )
    summaries = FakeSummaryRepo(
        by_version={
            ver_a.id: Summary(
                id=uuid.uuid4(),
                document_id=doc_a.id,
                created_by=user_id,
                source_version_id=ver_a.id,
                type=SummaryType.short,
                status=SummaryStatus.completed,
                content="Alpha covers onboarding and benefits.",
                sections=None,
                model_used="test",
                prompt_tokens=1,
                completion_tokens=1,
                cost_usd=0,
                latency_ms=1,
                created_at=datetime.now(UTC),
            ),
            ver_b.id: Summary(
                id=uuid.uuid4(),
                document_id=doc_b.id,
                created_by=user_id,
                source_version_id=ver_b.id,
                type=SummaryType.short,
                status=SummaryStatus.completed,
                content="Beta covers onboarding but not benefits.",
                sections=None,
                model_used="test",
                prompt_tokens=1,
                completion_tokens=1,
                cost_usd=0,
                latency_ms=1,
                created_at=datetime.now(UTC),
            ),
        }
    )
    comparisons = FakeComparisonRepo()
    session = FakeSession()
    captured: dict[str, Any] = {}

    async def fake_llm(**kwargs: Any) -> StructuredLlmResult:
        captured.update(kwargs)
        return StructuredLlmResult(
            data={
                "similarities": ["Both cover onboarding"],
                "differences": ["Only Alpha covers benefits"],
            },
            model=kwargs["model"],
            input_tokens=10,
            output_tokens=20,
            estimated_cost_usd=0.01,
        )

    settings = Settings(
        chat_llm_provider="anthropic",
        anthropic_api_key="test-key",
        chat_answer_light_model="claude-haiku-test",
        chat_answer_strong_model="claude-sonnet-test",
    )
    service = ComparisonService(
        settings=settings,
        session=session,  # type: ignore[arg-type]
        documents=documents,  # type: ignore[arg-type]
        retrieval=FakeRetrievalRepo(),  # type: ignore[arg-type]
        summaries=summaries,  # type: ignore[arg-type]
        comparisons=comparisons,  # type: ignore[arg-type]
        llm_call=fake_llm,
    )

    outcome = await service.create_comparison(
        workspace_id=workspace_id,
        document_ids=[doc_a.id, doc_b.id],
        created_by=user_id,
        focus="onboarding",
    )

    assert session.commits == 1
    assert outcome.document_ids == [doc_a.id, doc_b.id]
    assert outcome.comparison.result == {
        "similarities": ["Both cover onboarding"],
        "differences": ["Only Alpha covers benefits"],
    }
    assert captured["model"] == "claude-sonnet-test"
    assert "Focus constraint" in captured["system"]
    assert "Comparison focus: onboarding" in captured["user"]
    assert "Alpha covers onboarding" in captured["user"]


@pytest.mark.asyncio
async def test_create_comparison_falls_back_to_chunks_when_no_summary() -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    doc_a, ver_a = _ready_doc(workspace_id=workspace_id, title="A")
    doc_b, ver_b = _ready_doc(workspace_id=workspace_id, title="B")

    retrieval = FakeRetrievalRepo(
        chunks_by_version={
            ver_a.id: [_chunk(content="A says X=1", document_id=doc_a.id)],
            ver_b.id: [_chunk(content="B says X=2", document_id=doc_b.id)],
        }
    )

    async def fake_llm(**kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={"similarities": [], "differences": ["X differs: 1 vs 2"]},
            model=kwargs["model"],
            input_tokens=5,
            output_tokens=5,
            estimated_cost_usd=0.0,
        )

    service = ComparisonService(
        settings=Settings(chat_answer_strong_model="claude-sonnet-test"),
        session=FakeSession(),  # type: ignore[arg-type]
        documents=FakeDocumentRepo(  # type: ignore[arg-type]
            documents={doc_a.id: doc_a, doc_b.id: doc_b},
            versions={ver_a.id: ver_a, ver_b.id: ver_b},
        ),
        retrieval=retrieval,  # type: ignore[arg-type]
        summaries=FakeSummaryRepo(),  # type: ignore[arg-type]
        comparisons=FakeComparisonRepo(),  # type: ignore[arg-type]
        llm_call=fake_llm,
    )

    outcome = await service.create_comparison(
        workspace_id=workspace_id,
        document_ids=[doc_a.id, doc_b.id],
        created_by=user_id,
        focus="metrics",
    )

    assert retrieval.last_focus == "metrics"
    assert outcome.comparison.result["differences"] == ["X differs: 1 vs 2"]


@pytest.mark.asyncio
async def test_create_comparison_rejects_fewer_than_two_documents() -> None:
    service = ComparisonService(
        settings=Settings(),
        session=FakeSession(),  # type: ignore[arg-type]
        documents=FakeDocumentRepo(),  # type: ignore[arg-type]
        retrieval=FakeRetrievalRepo(),  # type: ignore[arg-type]
        summaries=FakeSummaryRepo(),  # type: ignore[arg-type]
        comparisons=FakeComparisonRepo(),  # type: ignore[arg-type]
        llm_call=None,
    )
    with pytest.raises(ComparisonServiceError) as exc:
        await service.create_comparison(
            workspace_id=uuid.uuid4(),
            document_ids=[uuid.uuid4()],
            created_by=uuid.uuid4(),
        )
    assert exc.value.code == "too_few_documents"
