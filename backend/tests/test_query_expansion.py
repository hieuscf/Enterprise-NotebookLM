# =============================================================================
# File: test_query_expansion.py
# Module/Service: Search Service / Hybrid Retrieval — Query Expansion
# Layer: Service
# Purpose: Unit tests for deterministic query-intent classification + BM25
#   lexical expansion (RAG answer-quality P1, spec §7-§9).
# Dependencies:
#   - pytest, app.services.retrieval.query_expansion
# Database/Table: N/A
# Related Modules: hybrid_retrieval_service, context_assembly
# =============================================================================

from __future__ import annotations

import pytest

from app.services.retrieval.query_expansion import (
    QueryIntent,
    classify_query_intent,
    expand_lexical_query,
    is_document_level_query,
)


@pytest.mark.parametrize(
    "query",
    [
        "Nội dung chính của tài liệu",
        "Tài liệu này trình bày kiến trúc hệ thống như thế nào?",
        "Tóm tắt tài liệu",
        "Tài liệu này nói về gì?",
    ],
)
def test_global_overview_queries_detected(query: str) -> None:
    assert classify_query_intent(query) is QueryIntent.global_overview
    assert is_document_level_query(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "Hợp đồng này quy định những nội dung gì?",
        "Các nghĩa vụ chính của các bên là gì?",
        "Điều kiện/thời hạn/chấm dứt của hợp đồng là gì?",
    ],
)
def test_contract_overview_queries_detected(query: str) -> None:
    assert classify_query_intent(query) is QueryIntent.contract_overview
    assert is_document_level_query(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "Ai là bên A?",
        "Ngày ký hợp đồng là ngày nào?",
        "Trong tài liệu có quy định về blockchain không?",
    ],
)
def test_focused_queries_not_document_level(query: str) -> None:
    assert classify_query_intent(query) is QueryIntent.focused
    assert is_document_level_query(query) is False


def test_expand_lexical_query_widens_global_queries() -> None:
    expanded = expand_lexical_query("Nội dung chính của tài liệu")
    assert expanded.startswith("Nội dung chính của tài liệu")
    assert "mục đích" in expanded
    assert "phạm vi" in expanded


def test_expand_lexical_query_uses_contract_vocabulary() -> None:
    expanded = expand_lexical_query("Hợp đồng này quy định những nội dung gì?")
    assert "các bên" in expanded
    assert "nghĩa vụ" in expanded


def test_expand_lexical_query_bounded_by_max_extra_terms() -> None:
    expanded = expand_lexical_query("Tóm tắt tài liệu", max_extra_terms=2)
    extra = expanded[len("Tóm tắt tài liệu") :].split()
    # 2 terms of up to 2 words each -> at most 4 extra words.
    assert len(extra) <= 4


def test_expand_lexical_query_leaves_focused_queries_untouched() -> None:
    q = "Ai là bên A?"
    assert expand_lexical_query(q) == q


def test_expand_lexical_query_empty_input() -> None:
    assert expand_lexical_query("") == ""
    assert expand_lexical_query("   ") == ""
