# =============================================================================
# File: test_section_extraction.py
# Module/Service: Query Router — Section Extraction (FR11)
# Layer: Service
# Purpose: Classifier + extraction tests for structure-aware section queries.
# Responsibilities:
#   - Route the 10 required listing/heading queries to section_extraction
#   - Extract parent 4 → children 4.1 / 4.2 in document order, 0 LLM
#   - Heading match must not produce a "no information" answer
# Dependencies:
#   - pytest, app.services.query_router.section_*
# Public Exports:
#   - N/A
# Database/Table: N/A (fake RetrievalRepository)
# Related Modules: SectionExtractionHandler, RuleBasedClassifier
# Important Notes: 0 live DB / LLM / vector search.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.ai.hierarchical_chunking.chunk_planner import plan_hierarchical_chunks
from app.ai.hierarchical_chunking.heading_tree_builder import build_heading_tree
from app.ai.hierarchical_chunking.markdown_parser import parse_markdown_lines
from app.ai.hierarchical_chunking.section_parser import (
    is_direct_child_number,
    parse_numbered_heading,
)
from app.models.enums import ChunkLayoutType, RouteType
from app.repositories.retrieval import ChunkHydrationRow
from app.services.query_router.classifier import build_rule_based_classifier
from app.services.query_router.handlers.section_extraction_handler import (
    SectionExtractionHandler,
)
from app.services.query_router.orchestrator import QueryOrchestrator
from app.services.query_router.section_branch import SectionExtractionBranch
from app.services.query_router.section_patterns import (
    SectionIntent,
    detect_section_intent,
)
from app.services.query_router.section_resolver import resolve_section_match

WS = uuid.uuid4()
DOC = uuid.uuid4()
VER = uuid.uuid4()

PARENT_ID = uuid.uuid4()
CHILD_41_ID = uuid.uuid4()
CHILD_42_ID = uuid.uuid4()
CONTENT_41_ID = uuid.uuid4()
CONTENT_42_ID = uuid.uuid4()

COTECCONS_MARKDOWN = """# 4. SỰ KIỆN QUAN TRỌNG TRONG KỲ

## 4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")

Hoàn tất thủ tục đăng ký ngày 30/06/2026.
Mục đích: thực hiện các hoạt động liên quan đến đầu tư và xây dựng.

## 4.2 Mua Công ty "Coteccons KZ" LLP ("CTD KZ LLP")

Tập đoàn mua 100% vốn góp ngày 08/07/2025.
Lĩnh vực kinh doanh chính: cung cấp dịch vụ xây dựng.
"""

REQUIRED_CASES: list[dict[str, Any]] = [
    {
        "query": "Các SỰ KIỆN QUAN TRỌNG TRONG KỲ",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4",
        "expected_subsections": ["4.1", "4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "các sự kiện quan trọng trong kỳ",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4",
        "expected_subsections": ["4.1", "4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "Sự kiện quan trọng trong kỳ là gì?",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4",
        "expected_subsections": ["4.1", "4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "Liệt kê các sự kiện quan trọng trong kỳ",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4",
        "expected_subsections": ["4.1", "4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "Mục 4 gồm những gì?",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4",
        "expected_subsections": ["4.1", "4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "Các mục con của mục 4",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4",
        "expected_subsections": ["4.1", "4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "Mục 4.1 nói về gì?",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4.1",
        "expected_subsections": ["4.1"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "Mục 4.2 nói về gì?",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4.2",
        "expected_subsections": ["4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "Các phần trong chương này",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4",
        "expected_subsections": ["4.1", "4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
    {
        "query": "Liệt kê các subsection của phần Sự kiện quan trọng trong kỳ",
        "expected_route": RouteType.section_extraction,
        "expected_section": "4",
        "expected_subsections": ["4.1", "4.2"],
        "expected_llm_calls": 0,
        "expected_citations": True,
    },
]


def _row(
    *,
    chunk_id: uuid.UUID,
    content: str,
    chunk_index: int,
    layout_type: ChunkLayoutType,
    parent_chunk_id: uuid.UUID | None = None,
    heading_path: str | None = None,
    depth: int | None = 0,
    page_number: int | None = 6,
) -> ChunkHydrationRow:
    return ChunkHydrationRow(
        chunk_id=chunk_id,
        document_id=DOC,
        document_version_id=VER,
        workspace_id=WS,
        content=content,
        title="Báo cáo",
        page_number=page_number,
        section=content if layout_type == ChunkLayoutType.heading else None,
        chunk_index=chunk_index,
        heading_path=heading_path,
        layout_type=layout_type,
        parent_chunk_id=parent_chunk_id,
        depth=depth,
    )


def _fixture_chunks() -> list[ChunkHydrationRow]:
    parent_title = "4. SỰ KIỆN QUAN TRỌNG TRONG KỲ"
    child_41 = (
        '4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. '
        '("CTD Sing")'
    )
    child_42 = '4.2 Mua Công ty "Coteccons KZ" LLP ("CTD KZ LLP")'
    return [
        _row(
            chunk_id=PARENT_ID,
            content=parent_title,
            chunk_index=0,
            layout_type=ChunkLayoutType.heading,
            heading_path=parent_title,
            depth=0,
        ),
        _row(
            chunk_id=CHILD_41_ID,
            content=child_41,
            chunk_index=1,
            layout_type=ChunkLayoutType.heading,
            parent_chunk_id=PARENT_ID,
            heading_path=f"{parent_title} > {child_41}",
            depth=1,
        ),
        _row(
            chunk_id=CONTENT_41_ID,
            content=(
                "Hoàn tất thủ tục đăng ký ngày 30/06/2026.\n"
                "Mục đích: thực hiện các hoạt động liên quan đến đầu tư và xây dựng."
            ),
            chunk_index=2,
            layout_type=ChunkLayoutType.paragraph,
            parent_chunk_id=CHILD_41_ID,
            heading_path=f"{parent_title} > {child_41}",
            depth=2,
        ),
        _row(
            chunk_id=CHILD_42_ID,
            content=child_42,
            chunk_index=3,
            layout_type=ChunkLayoutType.heading,
            parent_chunk_id=PARENT_ID,
            heading_path=f"{parent_title} > {child_42}",
            depth=1,
        ),
        _row(
            chunk_id=CONTENT_42_ID,
            content=(
                "Tập đoàn mua 100% vốn góp ngày 08/07/2025.\n"
                "Lĩnh vực kinh doanh chính: cung cấp dịch vụ xây dựng."
            ),
            chunk_index=4,
            layout_type=ChunkLayoutType.paragraph,
            parent_chunk_id=CHILD_42_ID,
            heading_path=f"{parent_title} > {child_42}",
            depth=2,
        ),
    ]


class FakeSectionRepo:
    """In-memory RetrievalRepository subset for section extraction."""

    def __init__(self, rows: list[ChunkHydrationRow] | None = None) -> None:
        self.rows = rows or _fixture_chunks()

    def _scoped(self, workspace_id: uuid.UUID) -> list[ChunkHydrationRow]:
        return [r for r in self.rows if r.workspace_id == workspace_id]

    async def search_heading_chunks(
        self,
        workspace_id: uuid.UUID,
        *,
        section_number: str | None = None,
        title_query: str | None = None,
        limit: int = 80,
    ) -> list[ChunkHydrationRow]:
        headings = [
            r
            for r in self._scoped(workspace_id)
            if r.layout_type == ChunkLayoutType.heading
        ]
        title = (title_query or "").strip().lower()
        number = (section_number or "").strip()
        if not title and not number:
            return headings[:limit]
        out: list[ChunkHydrationRow] = []
        for row in headings:
            hay = " ".join(
                filter(None, [row.content, row.section, row.heading_path])
            ).lower()
            if title and title in hay:
                out.append(row)
                continue
            if number and (
                hay.startswith(f"{number}.")
                or hay.startswith(f"{number} ")
                or hay == number
            ):
                out.append(row)
        return out[:limit]

    async def list_child_chunks(
        self,
        workspace_id: uuid.UUID,
        parent_chunk_id: uuid.UUID,
        *,
        headings_only: bool = False,
        limit: int = 200,
    ) -> list[ChunkHydrationRow]:
        rows = [
            r
            for r in self._scoped(workspace_id)
            if r.parent_chunk_id == parent_chunk_id
        ]
        if headings_only:
            rows = [r for r in rows if r.layout_type == ChunkLayoutType.heading]
        return rows[:limit]

    async def list_chunks_by_heading_path_prefix(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
        heading_path: str,
        *,
        limit: int = 200,
    ) -> list[ChunkHydrationRow]:
        path = heading_path or ""
        return [
            r
            for r in self._scoped(workspace_id)
            if r.document_version_id == document_version_id
            and r.heading_path
            and (r.heading_path == path or r.heading_path.startswith(f"{path} > "))
        ][:limit]

    async def list_version_heading_chunks(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
        *,
        limit: int = 400,
    ) -> list[ChunkHydrationRow]:
        return [
            r
            for r in self._scoped(workspace_id)
            if r.document_version_id == document_version_id
            and r.layout_type == ChunkLayoutType.heading
        ][:limit]

    async def list_chunks_in_index_range(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
        *,
        start_index: int,
        end_index: int | None,
        limit: int = 200,
    ) -> list[ChunkHydrationRow]:
        rows = [
            r
            for r in self._scoped(workspace_id)
            if r.document_version_id == document_version_id
            and r.chunk_index is not None
            and r.chunk_index >= start_index
            and (end_index is None or r.chunk_index < end_index)
        ]
        return rows[:limit]

    async def fetch_sibling_chunks(self, *args: Any, **kwargs: Any) -> list[ChunkHydrationRow]:
        del args, kwargs
        return []


# ---------------------------------------------------------------------------
# Parser / chunk hierarchy
# ---------------------------------------------------------------------------


def test_parse_numbered_heading_parent_and_children() -> None:
    parent = parse_numbered_heading("4. SỰ KIỆN QUAN TRỌNG TRONG KỲ")
    child = parse_numbered_heading(
        '4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd.'
    )
    assert parent.number == "4"
    assert parent.title.upper().startswith("SỰ KIỆN")
    assert child.number == "4.1"
    assert is_direct_child_number("4", "4.1")
    assert is_direct_child_number("4", "4.2")
    assert not is_direct_child_number("4", "4.1.1")
    assert not is_direct_child_number("4.1", "4.2")


def test_chunk_planner_preserves_numbered_hierarchy() -> None:
    root = build_heading_tree(parse_markdown_lines(COTECCONS_MARKDOWN))
    planned = plan_hierarchical_chunks(root)
    headings = [c for c in planned if c.layout_type == ChunkLayoutType.heading]
    numbers = [c.section_number for c in headings]
    assert numbers == ["4", "4.1", "4.2"]
    parent = next(c for c in headings if c.section_number == "4")
    child_ids = [
        c.temp_id for c in headings if c.parent_temp_id == parent.temp_id
    ]
    child_numbers = [
        c.section_number for c in headings if c.temp_id in set(child_ids)
    ]
    assert child_numbers == ["4.1", "4.2"]
    indexes = [c.chunk_index for c in headings]
    assert indexes == sorted(indexes)


# ---------------------------------------------------------------------------
# Intent / classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", REQUIRED_CASES, ids=lambda c: c["query"][:40])
def test_required_queries_detect_section_intent(case: dict[str, Any]) -> None:
    match = detect_section_intent(case["query"])
    assert match.matched is True
    assert match.intent in {
        SectionIntent.list_children,
        SectionIntent.section_content,
        SectionIntent.outline,
    }


@pytest.mark.parametrize("case", REQUIRED_CASES, ids=lambda c: c["query"][:40])
def test_required_queries_classify_section_extraction(case: dict[str, Any]) -> None:
    clf = build_rule_based_classifier()
    assert clf.classify(case["query"], WS) == case["expected_route"]


def test_document_listing_stays_metadata() -> None:
    clf = build_rule_based_classifier()
    assert clf.classify("Liệt kê tài liệu", WS) == RouteType.metadata
    assert clf.classify("Có bao nhiêu tài liệu?", WS) == RouteType.metadata


def test_short_factoid_not_stolen_by_section() -> None:
    clf = build_rule_based_classifier()
    assert clf.classify("AI là gì?", WS) == RouteType.factoid
    assert clf.classify("Tác giả là ai?", WS) == RouteType.factoid


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("case", REQUIRED_CASES, ids=lambda c: c["query"][:40])
async def test_required_queries_extract_ordered_subsections(
    case: dict[str, Any],
) -> None:
    handler = SectionExtractionHandler(retrieval_repo=FakeSectionRepo())  # type: ignore[arg-type]
    result = await handler.handle(workspace_id=WS, query_text=case["query"])

    assert result.route_type == RouteType.section_extraction
    assert result.metadata.get("llm_calls_count") == case["expected_llm_calls"]
    assert result.verify is True
    assert result.answer
    lowered = result.answer.lower()
    assert "theo các trích đoạn hiện có" not in lowered
    assert "không tìm thấy thông tin" not in lowered
    assert "chưa có thông tin" not in lowered

    section = result.metadata["section"]
    assert section["number"] == case["expected_section"]
    item_numbers = [item["number"] for item in result.metadata["items"]]
    assert item_numbers == case["expected_subsections"]
    assert item_numbers == sorted(
        item_numbers, key=lambda n: [int(p) for p in str(n).split(".")]
    )

    if case["expected_citations"]:
        assert result.citation_refs
        assert all(ref.verify for ref in result.citation_refs)
        assert all(ref.chunk_id is not None for ref in result.citation_refs)
        assert all(ref.page_number == 6 for ref in result.citation_refs if ref.page_number)

    if case["expected_section"] == "4" and case["expected_subsections"] == ["4.1", "4.2"]:
        assert "CTD Sing" in (result.answer or "")
        assert "CTD KZ" in (result.answer or "")
        assert result.answer.index("4.1") < result.answer.index("4.2")
        assert "1. 4.1" not in (result.answer or "")
        assert "2. 4.2" not in (result.answer or "")
        assert not any(
            line.lstrip().startswith(("- ", "* "))
            for line in (result.answer or "").splitlines()
        )


@pytest.mark.asyncio
async def test_heading_match_without_children_still_not_no_info() -> None:
    orphan = _row(
        chunk_id=PARENT_ID,
        content="4. SỰ KIỆN QUAN TRỌNG TRONG KỲ",
        chunk_index=0,
        layout_type=ChunkLayoutType.heading,
        heading_path="4. SỰ KIỆN QUAN TRỌNG TRONG KỲ",
        depth=0,
    )
    handler = SectionExtractionHandler(retrieval_repo=FakeSectionRepo([orphan]))  # type: ignore[arg-type]
    result = await handler.handle(
        workspace_id=WS, query_text="Các sự kiện quan trọng trong kỳ"
    )
    assert result.route_type == RouteType.section_extraction
    assert "không tìm thấy" not in (result.answer or "").lower()
    assert result.citation_refs


@pytest.mark.asyncio
async def test_unknown_section_falls_back_to_complex() -> None:
    handler = SectionExtractionHandler(retrieval_repo=FakeSectionRepo())  # type: ignore[arg-type]
    result = await handler.handle(
        workspace_id=WS, query_text="Mục 99 gồm những gì?"
    )
    assert result.route_type == RouteType.complex
    assert result.answer is None


@pytest.mark.asyncio
async def test_section_branch_zero_llm_and_citations() -> None:
    branch = SectionExtractionBranch(retrieval_repo=FakeSectionRepo())  # type: ignore[arg-type]
    result = await branch.execute(
        workspace_id=WS,
        query_text="Liệt kê các sự kiện quan trọng trong kỳ",
    )
    assert result.route_type == RouteType.section_extraction
    assert result.verify is True
    assert result.citation_refs
    assert "4.1" in (result.answer or "")


@pytest.mark.asyncio
async def test_orchestrator_section_extraction_logs_zero_llm() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services.query_router.schemas import RouteDecision

    class RecordingRepo:
        def __init__(self) -> None:
            self.rows: list[dict[str, Any]] = []

        async def create_log(self, **kwargs: Any) -> SimpleNamespace:
            row_id = uuid.uuid4()
            self.rows.append({"id": row_id, **kwargs})
            return SimpleNamespace(id=row_id)

        async def create_query_log(self, **kwargs: Any) -> SimpleNamespace:
            return await self.create_log(**kwargs)

    repo = RecordingRepo()
    router = AsyncMock()
    router.route = AsyncMock(
        return_value=RouteDecision(
            route_type=RouteType.section_extraction,
            reason="test",
            latency_ms=1,
            query_hash="h",
        )
    )
    orch = QueryOrchestrator(
        router=router,
        metadata_branch=AsyncMock(),
        factoid_branch=AsyncMock(),
        query_log_repository=repo,  # type: ignore[arg-type]
        section_branch=SectionExtractionBranch(
            retrieval_repo=FakeSectionRepo()  # type: ignore[arg-type]
        ),
    )
    result = await orch.handle_query(
        WS, uuid.uuid4(), "Các SỰ KIỆN QUAN TRỌNG TRONG KỲ"
    )
    assert result.route_type == RouteType.section_extraction
    assert result.llm_calls_count == 0
    assert result.citation_refs
    assert repo.rows[0]["route_type"] == RouteType.section_extraction
    assert repo.rows[0]["llm_calls_count"] == 0


def test_resolve_prefers_parent_number_over_child() -> None:
    from app.services.query_router.section_patterns import detect_section_intent

    intent = detect_section_intent("Mục 4 gồm những gì?")
    headings = [
        r for r in _fixture_chunks() if r.layout_type == ChunkLayoutType.heading
    ]
    best = resolve_section_match(intent, headings)
    assert best is not None
    assert best.number == "4"
    assert best.row.chunk_id == PARENT_ID


# ---------------------------------------------------------------------------
# Extractive citation provenance (0 LLM)
# ---------------------------------------------------------------------------


POLICY_PARENT_ID = uuid.uuid4()
POLICY_32_ID = uuid.uuid4()
POLICY_32_BODY_ID = uuid.uuid4()
POLICY_33_ID = uuid.uuid4()
POLICY_33_A_ID = uuid.uuid4()
POLICY_33_B_ID = uuid.uuid4()
POLICY_33_C_ID = uuid.uuid4()
POLICY_34_ID = uuid.uuid4()
POLICY_34_BODY_ID = uuid.uuid4()
POLICY_35_ID = uuid.uuid4()
POLICY_35_BODY_ID = uuid.uuid4()
POLICY_319_ID = uuid.uuid4()
POLICY_319_BODY_ID = uuid.uuid4()
POLICY_320_ID = uuid.uuid4()
POLICY_320_BODY_ID = uuid.uuid4()
DUP_BODY = "Chi phí xây dựng công trình dở dang được ghi nhận theo giá gốc."


def _policy_chunks(*, page_number: int | None = 12) -> list[ChunkHydrationRow]:
    parent_title = "3. TÓM TẮT CÁC CHÍNH SÁCH KẾ TOÁN CHỦ YẾU"
    children: list[tuple[uuid.UUID, str, str, uuid.UUID, str]] = [
        (
            POLICY_32_ID,
            "3.2 Các khoản phải thu",
            "Các khoản phải thu",
            POLICY_32_BODY_ID,
            "Phải thu khách hàng được theo dõi theo từng đối tượng.",
        ),
        (
            POLICY_33_ID,
            "3.3 Hàng tồn kho",
            "Hàng tồn kho",
            POLICY_33_A_ID,
            "Công ty áp dụng phương pháp kê khai thường xuyên.",
        ),
        (
            POLICY_34_ID,
            "3.4 Tài sản cố định hữu hình",
            "Tài sản cố định hữu hình",
            POLICY_34_BODY_ID,
            "TSCĐ hữu hình được ghi nhận theo nguyên giá.",
        ),
        (
            POLICY_35_ID,
            "3.5 Tài sản cố định vô hình",
            "Tài sản cố định vô hình",
            POLICY_35_BODY_ID,
            "TSCĐ vô hình được khấu hao theo đường thẳng.",
        ),
        (
            POLICY_319_ID,
            "3.19 Ghi nhận doanh thu",
            "Ghi nhận doanh thu",
            POLICY_319_BODY_ID,
            "Doanh thu được ghi nhận khi đã chuyển giao rủi ro.",
        ),
        (
            POLICY_320_ID,
            "3.20 Thuế",
            "Thuế",
            POLICY_320_BODY_ID,
            "Thuế thu nhập doanh nghiệp theo thuế suất hiện hành.",
        ),
    ]
    rows = [
        _row(
            chunk_id=POLICY_PARENT_ID,
            content=parent_title,
            chunk_index=0,
            layout_type=ChunkLayoutType.heading,
            heading_path=parent_title,
            depth=0,
            page_number=page_number,
        )
    ]
    index = 1
    for heading_id, heading_text, _title, body_id, body in children:
        heading_path = f"{parent_title} > {heading_text}"
        rows.append(
            _row(
                chunk_id=heading_id,
                content=heading_text,
                chunk_index=index,
                layout_type=ChunkLayoutType.heading,
                parent_chunk_id=POLICY_PARENT_ID,
                heading_path=heading_path,
                depth=1,
                page_number=page_number,
            )
        )
        index += 1
        extra_bodies = [(body_id, body)]
        if heading_id == POLICY_33_ID:
            extra_bodies = [
                (POLICY_33_A_ID, body),
                (POLICY_33_B_ID, DUP_BODY),
                (POLICY_33_C_ID, DUP_BODY),
            ]
        for extra_id, extra_text in extra_bodies:
            rows.append(
                _row(
                    chunk_id=extra_id,
                    content=extra_text,
                    chunk_index=index,
                    layout_type=ChunkLayoutType.paragraph,
                    parent_chunk_id=heading_id,
                    heading_path=heading_path,
                    depth=2,
                    page_number=page_number,
                )
            )
            index += 1
    return rows


class RecordingRetrievalRecords:
    """Captures extractive retrieval persistence without a live DB."""

    def __init__(self) -> None:
        self.insert_calls: list[dict[str, Any]] = []

    async def insert_candidates(self, **kwargs: Any) -> int:
        self.insert_calls.append(kwargs)
        return len(kwargs.get("candidates") or [])

    async def list_integrity_for_cited_chunks(self, **kwargs: Any) -> list[Any]:
        del kwargs
        return []


@pytest.mark.asyncio
async def test_accounting_policies_parent_has_verified_citations() -> None:
    """Test 1 + Test 7: parent section lists children, each with provenance."""
    handler = SectionExtractionHandler(
        retrieval_repo=FakeSectionRepo(_policy_chunks())  # type: ignore[arg-type]
    )
    result = await handler.handle(
        workspace_id=WS, query_text="CÁC CHÍNH SÁCH KẾ TOÁN CHỦ YẾU"
    )
    assert result.route_type == RouteType.section_extraction
    assert result.metadata.get("llm_calls_count") == 0
    assert result.metadata.get("answer_type") == "extractive"
    assert result.citation_refs
    assert all(ref.verify for ref in result.citation_refs)
    assert all(ref.chunk_id is not None for ref in result.citation_refs)
    assert all(ref.document_id == DOC for ref in result.citation_refs)
    assert all(ref.document_version_id == VER for ref in result.citation_refs)
    item_numbers = [item["number"] for item in result.metadata["items"]]
    assert item_numbers == ["3.2", "3.3", "3.4", "3.5", "3.19", "3.20"]
    for item in result.metadata["items"]:
        assert item["citations"]
        assert all(c["chunk_id"] for c in item["citations"])
    lowered = (result.answer or "").lower()
    assert "không tìm thấy nguồn xác thực" not in lowered


@pytest.mark.asyncio
async def test_section_3_3_citation_chunk_id_verified() -> None:
    """Test 2: leaf section keeps chunk_id and verified provenance."""
    handler = SectionExtractionHandler(
        retrieval_repo=FakeSectionRepo(_policy_chunks())  # type: ignore[arg-type]
    )
    result = await handler.handle(workspace_id=WS, query_text="3.3 Hàng tồn kho")
    assert result.route_type == RouteType.section_extraction
    assert result.metadata["section"]["number"] == "3.3"
    assert result.citation_refs
    assert all(ref.chunk_id is not None for ref in result.citation_refs)
    assert all(ref.verify for ref in result.citation_refs)
    cited = {ref.chunk_id for ref in result.citation_refs}
    assert POLICY_33_A_ID in cited
    assert POLICY_33_B_ID in cited
    assert POLICY_33_C_ID in cited


@pytest.mark.asyncio
async def test_merged_body_chunks_keep_three_provenance_refs() -> None:
    """Test 3: 3.3 heading + three body chunks → one heading, three provenance."""
    handler = SectionExtractionHandler(
        retrieval_repo=FakeSectionRepo(_policy_chunks())  # type: ignore[arg-type]
    )
    result = await handler.handle(workspace_id=WS, query_text="3.3 Hàng tồn kho")
    items = result.metadata["items"]
    assert [item["number"] for item in items] == ["3.3"]
    chunk_ids = [uuid.UUID(cid) for cid in items[0]["chunk_ids"]]
    assert POLICY_33_ID in chunk_ids
    assert {POLICY_33_A_ID, POLICY_33_B_ID, POLICY_33_C_ID}.issubset(set(chunk_ids))
    body_ids = [
        uuid.UUID(c["chunk_id"])
        for c in items[0]["citations"]
        if uuid.UUID(c["chunk_id"]) != POLICY_33_ID
    ]
    assert set(body_ids) == {POLICY_33_A_ID, POLICY_33_B_ID, POLICY_33_C_ID}


@pytest.mark.asyncio
async def test_null_page_number_is_still_valid_citation() -> None:
    """Test 4: missing page is not a citation failure when chunk_id exists."""
    handler = SectionExtractionHandler(
        retrieval_repo=FakeSectionRepo(_policy_chunks(page_number=None))  # type: ignore[arg-type]
    )
    result = await handler.handle(
        workspace_id=WS, query_text="CÁC CHÍNH SÁCH KẾ TOÁN CHỦ YẾU"
    )
    assert result.citation_refs
    assert all(ref.page_number is None for ref in result.citation_refs)
    assert all(ref.verify is True for ref in result.citation_refs)
    assert all(ref.chunk_id is not None for ref in result.citation_refs)


@pytest.mark.asyncio
async def test_duplicate_body_dedupes_text_keeps_provenance() -> None:
    """Test 5: identical body text is rendered once; both chunk ids remain."""
    handler = SectionExtractionHandler(
        retrieval_repo=FakeSectionRepo(_policy_chunks())  # type: ignore[arg-type]
    )
    result = await handler.handle(workspace_id=WS, query_text="3.3 Hàng tồn kho")
    answer = result.answer or ""
    assert answer.count(DUP_BODY) == 1
    cited = {ref.chunk_id for ref in result.citation_refs}
    assert POLICY_33_B_ID in cited
    assert POLICY_33_C_ID in cited


@pytest.mark.asyncio
async def test_unknown_heading_falls_back_to_hybrid_rag() -> None:
    """Test 8: no heading → section_extraction handler downgrades to complex."""
    handler = SectionExtractionHandler(retrieval_repo=FakeSectionRepo())  # type: ignore[arg-type]
    result = await handler.handle(
        workspace_id=WS, query_text="Mục không tồn tại gồm những gì?"
    )
    assert result.route_type == RouteType.complex
    assert result.answer is None


@pytest.mark.asyncio
async def test_orchestrator_persists_extractive_retrievals() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services.query_router.schemas import RouteDecision

    class RecordingRepo:
        def __init__(self) -> None:
            self.rows: list[dict[str, Any]] = []

        async def create_log(self, **kwargs: Any) -> SimpleNamespace:
            row_id = uuid.uuid4()
            self.rows.append({"id": row_id, **kwargs})
            return SimpleNamespace(id=row_id)

        async def create_query_log(self, **kwargs: Any) -> SimpleNamespace:
            return await self.create_log(**kwargs)

    logs = RecordingRepo()
    retrievals = RecordingRetrievalRecords()
    router = AsyncMock()
    router.route = AsyncMock(
        return_value=RouteDecision(
            route_type=RouteType.section_extraction,
            reason="test",
            latency_ms=1,
            query_hash="h",
        )
    )
    message_id = uuid.uuid4()
    orch = QueryOrchestrator(
        router=router,
        metadata_branch=AsyncMock(),
        factoid_branch=AsyncMock(),
        query_log_repository=logs,  # type: ignore[arg-type]
        section_branch=SectionExtractionBranch(
            retrieval_repo=FakeSectionRepo(_policy_chunks())  # type: ignore[arg-type]
        ),
        retrieval_records=retrievals,  # type: ignore[arg-type]
    )
    result = await orch.handle_query(
        WS,
        uuid.uuid4(),
        "CÁC CHÍNH SÁCH KẾ TOÁN CHỦ YẾU",
        message_id=message_id,
    )
    assert result.route_type == RouteType.section_extraction
    assert result.llm_calls_count == 0
    assert result.citation_refs
    assert all(ref.verify for ref in result.citation_refs)
    assert retrievals.insert_calls
    candidates = retrievals.insert_calls[0]["candidates"]
    assert candidates
    assert all(c.chunk_id is not None for c in candidates)
    assert retrievals.insert_calls[0]["message_id"] == message_id
    assert retrievals.insert_calls[0]["retrieval_pass"] == 1
