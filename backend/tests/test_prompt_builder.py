# =============================================================================
# File: test_prompt_builder.py
# Module/Service: Chat Service / Prompt Construction (FR4)
# Layer: Service
# Purpose: Unit tests for build_prompt() hierarchical rendering, UUID-free
#   prose, and query-type synthesis hints (RAG answer-quality P1, §5-§6, §10).
# Dependencies:
#   - pytest, app.services.chat.prompt_builder
# Database/Table: N/A
# Related Modules: context_assembly, answer_generator, prompt_templates
# =============================================================================

from __future__ import annotations

import uuid

from app.services.chat.prompt_builder import (
    PromptRetrievalItem,
    build_prompt,
    retrieval_candidates_to_prompt_items,
)


def _item(**overrides: object) -> PromptRetrievalItem:
    base: dict[str, object] = {
        "citation_id": "1",
        "text_snippet": "nội dung đoạn văn",
        "document_id": str(uuid.uuid4()),
        "rank": 1,
        "document_title": "Hợp đồng ủy quyền",
        "section_title": "Điều 2",
        "heading_path": "HỢP ĐỒNG > Điều 2",
        "page_number": 2,
    }
    base.update(overrides)
    return PromptRetrievalItem(**base)  # type: ignore[arg-type]


def test_build_prompt_renders_document_and_section_headers() -> None:
    item = _item()
    built = build_prompt("SYSTEM", None, [item], "Ai là bên A?")
    assert "[Tài liệu] Hợp đồng ủy quyền" in built.user
    assert "[Phần] HỢP ĐỒNG > Điều 2" in built.user
    assert "(Trang 2)" in built.user
    assert f"[{item.citation_id}]" in built.user


def test_build_prompt_never_exposes_raw_document_uuid_as_prose() -> None:
    doc_id = str(uuid.uuid4())
    item = _item(document_id=doc_id, document_title=None)
    built = build_prompt("SYSTEM", None, [item], "Nội dung chính của tài liệu")
    assert doc_id not in built.user
    assert "[Tài liệu] tài liệu" in built.user


def test_build_prompt_groups_consecutive_chunks_same_doc_section() -> None:
    item1 = _item(citation_id="1")
    item2 = _item(citation_id="2")
    built = build_prompt("SYSTEM", None, [item1, item2], "Ai là bên A?")
    # Header should render once, not once per chunk.
    assert built.user.count("[Tài liệu] Hợp đồng ủy quyền") == 1
    assert built.user.count("[Phần] HỢP ĐỒNG > Điều 2") == 1


def test_build_prompt_repeats_headers_when_section_changes() -> None:
    item1 = _item(citation_id="1", section_title="Điều 1", heading_path="HỢP ĐỒNG > Điều 1")
    item2 = _item(citation_id="2", section_title="Điều 2", heading_path="HỢP ĐỒNG > Điều 2")
    built = build_prompt("SYSTEM", None, [item1, item2], "Ai là bên A?")
    assert "[Phần] HỢP ĐỒNG > Điều 1" in built.user
    assert "[Phần] HỢP ĐỒNG > Điều 2" in built.user


def test_build_prompt_adds_global_synthesis_hint_for_overview_questions() -> None:
    built = build_prompt("SYSTEM", None, [_item()], "Nội dung chính của tài liệu")
    assert "tổng hợp" in built.user
    assert "NHIỀU đoạn trích" in built.user


def test_build_prompt_adds_contract_synthesis_hint_for_contract_questions() -> None:
    built = build_prompt("SYSTEM", None, [_item()], "Hợp đồng này quy định những nội dung gì?")
    assert "điều khoản" in built.user
    assert "không suy đoán" in built.user


def test_build_prompt_no_synthesis_hint_for_focused_questions() -> None:
    built = build_prompt("SYSTEM", None, [_item()], "Ai là bên A?")
    assert "tổng hợp (synthesize)" not in built.user
    assert "không suy đoán các mục còn thiếu" not in built.user


def test_build_prompt_handles_empty_context() -> None:
    built = build_prompt("SYSTEM", None, [], "Ai là bên A?")
    assert "Retrieved context: (none)" in built.user


def test_retrieval_candidates_to_prompt_items_maps_hierarchical_metadata() -> None:
    class FakeCandidate:
        def __init__(self) -> None:
            self.chunk_id = uuid.uuid4()
            self.text_snippet = "text"
            self.document_id = uuid.uuid4()
            self.rank = 3
            self.document_title = "Doc Title"
            self.section_title = "Section A"
            self.heading_path = "Doc > Section A"
            self.page_number = 5

    items = retrieval_candidates_to_prompt_items([FakeCandidate()])
    assert len(items) == 1
    mapped = items[0]
    assert mapped.document_title == "Doc Title"
    assert mapped.section_title == "Section A"
    assert mapped.heading_path == "Doc > Section A"
    assert mapped.page_number == 5


def test_retrieval_candidates_to_prompt_items_skips_missing_chunk_id() -> None:
    class FakeCandidate:
        chunk_id = None
        text_snippet = "text"

    items = retrieval_candidates_to_prompt_items([FakeCandidate()])
    assert items == []
