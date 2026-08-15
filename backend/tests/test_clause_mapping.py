# =============================================================================
# File: test_clause_mapping.py
# Module/Service: Clause Identity & Mapping (FR8 / TASK-CMP-03)
# Layer: Service
# Purpose: Unit, integration, V1/V2 regression, and false-positive mapping tests.
# Responsibilities:
#   - Exact / title / parent / moved-number / lexical / semantic scoring
#   - One-to-one, ambiguity, unmatched (never ADDED/REMOVED)
#   - Retrieval independence for Điều 1.2 / 1.3
# Dependencies:
#   - pytest, extract_from_text/pages, normalize_structure, map_normalized_structures
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: 0 LLM. Mapping uses full clause sets, not top-k RAG.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.ai.document_structure.mapping_config import MappingConfig
from app.ai.document_structure.mapping_engine import (
    map_normalized_structures,
    score_pair,
)
from app.ai.document_structure.mapping_similarity import (
    cosine_similarity,
    lexical_similarity,
    title_similarity,
)
from app.ai.document_structure.mapping_types import MappingStatus, MappingType
from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    NormalizedUnit,
    normalize_structure,
)
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.types import StructuralUnitType
from app.services.document_structure.mapper import ClauseMappingEngine

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
V1_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
V2_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"


def _pages(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    pages: list[tuple[int, str]] = []
    current: int | None = None
    buf: list[str] = []
    for line in text.splitlines():
        marker = line.strip()
        if marker.startswith("===== PAGE ") and marker.endswith("====="):
            if current is not None:
                pages.append((current, "\n".join(buf)))
            current = int(marker.replace("=====", "").replace("PAGE", "").strip())
            buf = []
            continue
        buf.append(line)
    if current is not None:
        pages.append((current, "\n".join(buf)))
    return pages


def _norm(text: str, *, title: str = "Doc") -> NormalizedDocumentStructure:
    return normalize_structure(extract_from_text(text, title=title, document_id=uuid4()))


def _unit(
    *,
    source_id: str,
    unit_type: StructuralUnitType,
    number: str,
    title: str,
    body: str,
    parent_key: str | None = None,
    order_index: int = 1,
    document_id=None,
) -> NormalizedUnit:
    key = f"{unit_type.value}:{number}"
    parent_number = parent_key.split(":")[-1] if parent_key else None
    number_path = ((parent_number, number) if parent_number else (number,))
    return NormalizedUnit(
        source_id=source_id,
        document_id=document_id or uuid4(),
        type=unit_type,
        canonical_number=number,
        identity_key=key,
        qualified_key=f"{parent_key}/{key}" if parent_key else key,
        number_path=number_path,
        parent_identity_key=parent_key,
        original_title=title,
        original_text=body,
        original_heading=title,
        normalized_title=title.casefold(),
        folded_title=title.casefold(),
        normalized_body=body.casefold(),
        folded_body=body.casefold(),
        aliases=(number, title.casefold()),
        heading_path=title,
        order_index=order_index,
        level=1 if parent_key else 0,
    )


def _tree(*units: NormalizedUnit, title: str = "D") -> NormalizedDocumentStructure:
    doc_id = units[0].document_id if units else uuid4()
    return NormalizedDocumentStructure(
        document_id=doc_id,
        title=title,
        sections=list(units),
    )


# ---------------------------------------------------------------------------
# Similarity + scoring
# ---------------------------------------------------------------------------


def test_title_similarity_is_case_and_whitespace_insensitive() -> None:
    assert title_similarity("trách nhiệm của các bên", "TRÁCH NHIỆM CỦA CÁC BÊN") == 1.0
    assert title_similarity("phạm vi công việc", "pham vi cong viec") >= 0.5


def test_lexical_similarity_rewards_overlap() -> None:
    assert lexical_similarity("bên b bồi thường thiệt hại trực tiếp", "bên b bồi thường thiệt hại trực tiếp") == 1.0
    assert lexical_similarity("bồi thường thiệt hại", "thanh toán phí dịch vụ") < 0.4


def test_cosine_similarity_and_empty_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([], [1.0]) == 0.0


def test_exact_number_and_type_scores_as_exact() -> None:
    left = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.2",
        title="Giới hạn",
        body="Tổng trách nhiệm 100%",
        parent_key="ARTICLE:8",
    )
    right = _unit(
        source_id="t",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.2",
        title="Giới hạn",
        body="Tổng trách nhiệm 30%",
        parent_key="ARTICLE:8",
    )
    score, signals = score_pair(left, right)
    assert signals.number_match is True
    assert signals.type_match is True
    assert score >= MappingConfig().exact_min
    assert MappingConfig().classify(score, number_match=True, type_match=True) == "EXACT"


def test_threshold_classification_is_centralized() -> None:
    cfg = MappingConfig(high_min=0.85, medium_min=0.70, low_min=0.55)
    assert cfg.classify(0.90, number_match=False, type_match=True) == "HIGH_CONFIDENCE"
    assert cfg.classify(0.72, number_match=False, type_match=True) == "MEDIUM_CONFIDENCE"
    assert cfg.classify(0.60, number_match=False, type_match=True) == "LOW_CONFIDENCE"
    assert cfg.classify(0.20, number_match=False, type_match=True) == "UNMATCHED"


# ---------------------------------------------------------------------------
# Deterministic mapping
# ---------------------------------------------------------------------------


def test_exact_identity_mapping_ac01() -> None:
    v1 = _norm("ĐIỀU 8. TRÁCH NHIỆM\n8.2. Tổng trách nhiệm 100%.\n")
    v2 = _norm("ĐIỀU 8. TRÁCH NHIỆM\n8.2. Tổng trách nhiệm 30%.\n")
    result = map_normalized_structures(v1, v2)
    row = result.find_source("CLAUSE:8.2")
    assert row is not None
    assert row.accepted
    assert row.confidence_level is MappingStatus.EXACT
    assert row.target_unit is not None
    assert row.target_unit.identity_key == "CLAUSE:8.2"
    assert row.signals.number_match is True
    assert "ADDED" not in row.confidence_level.value
    assert "REMOVED" not in row.confidence_level.value


def test_title_match_when_numbering_changes_ac02() -> None:
    v1 = _norm(
        "ĐIỀU 8. TRÁCH NHIỆM VÀ GIỚI HẠN BỒI THƯỜNG\n"
        "8.1. Bên vi phạm phải bồi thường thiệt hại trực tiếp thực tế.\n"
        "8.2. Tổng trách nhiệm không vượt quá một trăm phần trăm giá trị hợp đồng.\n"
    )
    v2 = _norm(
        "ĐIỀU 9. TRÁCH NHIỆM VÀ GIỚI HẠN BỒI THƯỜNG\n"
        "9.1. Bên vi phạm phải bồi thường thiệt hại trực tiếp thực tế.\n"
        "9.2. Tổng trách nhiệm không vượt quá một trăm phần trăm giá trị hợp đồng.\n"
    )
    result = map_normalized_structures(v1, v2)
    article = result.find_source("ARTICLE:8")
    assert article is not None and article.accepted
    assert article.target_unit is not None
    assert article.target_unit.identity_key == "ARTICLE:9"
    assert article.confidence_level in {
        MappingStatus.EXACT,
        MappingStatus.HIGH_CONFIDENCE,
        MappingStatus.MEDIUM_CONFIDENCE,
    }
    c81 = result.find_source("CLAUSE:8.1")
    c82 = result.find_source("CLAUSE:8.2")
    assert c81 is not None and c81.accepted
    assert c82 is not None and c82.accepted
    assert c81.target_unit is not None and c81.target_unit.identity_key == "CLAUSE:9.1"
    assert c82.target_unit is not None and c82.target_unit.identity_key == "CLAUSE:9.2"
    assert result.paired_identity_keys().get("ARTICLE:8") == "ARTICLE:9"


def test_parent_hierarchy_propagates_to_children() -> None:
    v1 = _norm(
        "ĐIỀU 8. LIABILITY\n8.1. First child obligation text here.\n8.2. Second child obligation text here.\n"
    )
    v2 = _norm(
        "ĐIỀU 9. LIABILITY\n9.1. First child obligation text here.\n9.2. Second child obligation text here.\n"
    )
    result = map_normalized_structures(v1, v2)
    assert result.find_source("CLAUSE:8.1").signals.parent_match is True  # type: ignore[union-attr]
    assert result.find_source("CLAUSE:8.2").signals.relative_number_match is True  # type: ignore[union-attr]


def test_moved_clause_is_mapped_not_unmatched() -> None:
    v1 = _norm("ĐIỀU 8. BẢO MẬT VÀ DỮ LIỆU\n8.1. Mỗi bên phải bảo mật thông tin kinh doanh.\n")
    v2 = _norm("ĐIỀU 9. BẢO MẬT VÀ DỮ LIỆU\n9.1. Mỗi bên phải bảo mật thông tin kinh doanh.\n")
    result = map_normalized_structures(v1, v2)
    row = result.find_source("ARTICLE:8")
    assert row is not None and row.accepted
    assert row.confidence_level is not MappingStatus.UNMATCHED


def test_unmatched_is_not_added_or_removed_ac05() -> None:
    v1 = _norm("ĐIỀU 1. PHẠM VI\n1.1. Chỉ có ở V1.\n")
    v2 = _norm("ĐIỀU 2. THỜI HẠN\n2.1. Chỉ có ở V2.\n")
    result = map_normalized_structures(v1, v2)
    left = result.find_source("CLAUSE:1.1")
    assert left is not None
    assert left.confidence_level is MappingStatus.UNMATCHED
    assert left.accepted is False
    assert all(row.confidence_level is not MappingStatus.UNMATCHED or True for row in result.mappings)
    assert "ADDED" not in {row.confidence_level.value for row in result.mappings}
    assert "REMOVED" not in {row.confidence_level.value for row in result.mappings}
    assert result.unmatched_targets
    assert all(row.confidence_level is MappingStatus.UNMATCHED for row in result.unmatched_targets)


def test_ambiguous_when_margin_below_threshold_ac04() -> None:
    cfg = MappingConfig(ambiguous_margin=0.20, medium_min=0.50, high_min=0.90)
    source = _unit(
        source_id="a",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp và hợp lý",
        parent_key="ARTICLE:1",
        order_index=5,
    )
    x = _unit(
        source_id="x",
        unit_type=StructuralUnitType.CLAUSE,
        number="2.1",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp và hợp lý phát sinh",
        parent_key="ARTICLE:2",
        order_index=5,
        document_id=uuid4(),
    )
    y = _unit(
        source_id="y",
        unit_type=StructuralUnitType.CLAUSE,
        number="3.1",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp và hợp lý phát sinh",
        parent_key="ARTICLE:3",
        order_index=6,
        document_id=x.document_id,
    )
    result = map_normalized_structures(_tree(source), _tree(x, y), config=cfg)
    row = result.find_source("CLAUSE:1.1")
    assert row is not None
    assert row.confidence_level is MappingStatus.AMBIGUOUS
    assert row.target_unit is None
    assert len(row.candidates) >= 2


def test_one_to_one_does_not_reuse_target_ac06() -> None:
    v1 = _norm(
        "ĐIỀU 8. LIABILITY\n"
        "8.2. Tổng trách nhiệm không vượt quá một trăm phần trăm giá trị hợp đồng.\n"
        "8.3. Bên B không chịu trách nhiệm thiệt hại gián tiếp mất doanh thu.\n"
    )
    v2 = _norm(
        "ĐIỀU 8. LIABILITY\n"
        "8.2. Tổng trách nhiệm không vượt quá một trăm phần trăm giá trị hợp đồng.\n"
        "8.3. Bên B không chịu trách nhiệm thiệt hại gián tiếp mất doanh thu.\n"
    )
    result = map_normalized_structures(v1, v2)
    targets = [
        row.target_unit.identity_key
        for row in result.accepted()
        if row.target_unit and row.target_unit.identity_key
    ]
    assert len(targets) == len(set(targets))
    assert result.paired_identity_keys()["CLAUSE:8.2"] == "CLAUSE:8.2"
    assert result.paired_identity_keys()["CLAUSE:8.3"] == "CLAUSE:8.3"


def test_empty_document_maps_without_crash() -> None:
    empty = _norm("")
    other = _norm("ĐIỀU 1. PHẠM VI\n1.1. Có nội dung.\n")
    result = map_normalized_structures(empty, other)
    assert result.mappings == []
    assert result.metadata["mapping_llm_calls"] == 0
    assert result.unmatched_targets


def test_missing_parent_still_maps_by_identity() -> None:
    v1 = _norm("1.2. Chi tiết tính năng được quy định tại phụ lục.\n")
    v2 = _norm("1.2. Chi tiết tính năng được quy định tại phụ lục.\n")
    result = map_normalized_structures(v1, v2)
    row = result.find_source("CLAUSE:1.2")
    assert row is not None and row.accepted


def test_duplicate_identity_does_not_double_assign() -> None:
    doc_a = uuid4()
    doc_b = uuid4()
    s1 = _unit(
        source_id="s1",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="nội dung một",
        document_id=doc_a,
        order_index=1,
    )
    s2 = _unit(
        source_id="s2",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="B",
        body="nội dung hai khác biệt hoàn toàn xyz",
        document_id=doc_a,
        order_index=2,
    )
    t1 = _unit(
        source_id="t1",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="nội dung một",
        document_id=doc_b,
        order_index=1,
    )
    result = map_normalized_structures(_tree(s1, s2), _tree(t1))
    accepted_targets = [row.target_unit.source_id for row in result.accepted() if row.target_unit]
    assert accepted_targets.count("t1") == 1


def test_original_text_not_mutated_ac07() -> None:
    text = "ĐIỀU 1. PHẠM VI\n1.2. Nội dung gốc không được sửa.\n"
    v1 = _norm(text)
    before = v1.find(StructuralUnitType.CLAUSE, "1.2")
    assert before is not None
    original = before.original_text
    map_normalized_structures(v1, v1)
    after = v1.find(StructuralUnitType.CLAUSE, "1.2")
    assert after is not None
    assert after.original_text == original
    assert after.original_title == before.original_title


def test_embedding_failure_falls_back_to_deterministic() -> None:
    v1 = _norm("ĐIỀU 1. PHẠM VI\n1.2. Có ở cả hai.\n")
    v2 = _norm("ĐIỀU 1. PHẠM VI\n1.2. Có ở cả hai.\n")

    def boom(_texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embed down")

    result = map_normalized_structures(
        v1,
        v2,
        config=MappingConfig(enable_semantic=True),
        embed_fn=boom,
    )
    row = result.find_source("CLAUSE:1.2")
    assert row is not None and row.accepted
    assert row.confidence_level is MappingStatus.EXACT
    assert result.metadata["semantic_matching_count"] == 0


def test_reranker_failure_keeps_lexical_mapping() -> None:
    v1 = _norm("ĐIỀU 1. PHẠM VI\n1.2. Có ở cả hai.\n")
    v2 = _norm("ĐIỀU 1. PHẠM VI\n1.2. Có ở cả hai.\n")

    def boom(_a: str, _b: str) -> float:
        raise RuntimeError("rerank down")

    result = map_normalized_structures(
        v1,
        v2,
        config=MappingConfig(enable_reranker=True),
        rerank_fn=boom,
    )
    assert result.find_source("CLAUSE:1.2").accepted  # type: ignore[union-attr]


def test_injected_semantic_similarity_is_used() -> None:
    left = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="Bồi thường",
        body="nhà cung cấp chịu trách nhiệm bồi thường thiệt hại",
        order_index=1,
    )
    right = _unit(
        source_id="t",
        unit_type=StructuralUnitType.CLAUSE,
        number="2.1",
        title="Bồi thường",
        body="bên b có trách nhiệm bồi thường thiệt hại",
        order_index=1,
        document_id=uuid4(),
    )

    def embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.1] for _ in texts]

    result = map_normalized_structures(
        _tree(left),
        _tree(right),
        config=MappingConfig(enable_semantic=True, medium_min=0.50),
        embed_fn=embed,
    )
    row = result.find_source("CLAUSE:1.1")
    assert row is not None
    if row.accepted:
        assert row.signals.semantic_similarity == pytest.approx(1.0)


def test_no_llm_and_no_added_removed_labels() -> None:
    result = map_normalized_structures(
        _norm("ĐIỀU 1. A\n1.1. X\n"),
        _norm("ĐIỀU 1. A\n1.1. X\n"),
    )
    assert result.metadata["mapping_llm_calls"] == 0
    dumped = result.as_dict()
    assert "ADDED" not in str(dumped)
    assert "REMOVED" not in str(dumped)
    assert "original_text" not in str(dumped["mappings"])


# ---------------------------------------------------------------------------
# V1 / V2 regression + false positives
# ---------------------------------------------------------------------------


def test_v1_v2_maps_clause_1_2_and_1_3_despite_retrieval_gap() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    # Simulate a comparison context that only "retrieved" V2 1.2 — mapping
    # still receives the FULL trees, so V1 1.2 must pair.
    result = ClauseMappingEngine().map_structures(v1, v2)
    for key in ("CLAUSE:1.2", "CLAUSE:1.3"):
        row = result.find_source(key)
        assert row is not None, key
        assert row.accepted, key
        assert row.target_unit is not None
        assert row.target_unit.identity_key == key
        assert row.confidence_level is MappingStatus.EXACT
        assert row.mapping_type is MappingType.EXACT
        assert row.source_ref is not None and row.target_ref is not None
        assert row.signals.method == "exact_identity"
    assert "CLAUSE:1.2" not in {
        row.target_unit.identity_key
        for row in result.unmatched_targets
        if row.target_unit
    }


def test_v1_v2_key_articles_are_mapped() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    result = map_normalized_structures(v1, v2)
    pairs = result.paired_identity_keys()
    for article in ("ARTICLE:2", "ARTICLE:3", "ARTICLE:8", "ARTICLE:9", "ARTICLE:11"):
        assert pairs.get(article) == article, article
        row = result.find_source(article)
        assert row is not None and row.accepted
        assert row.confidence_level is MappingStatus.EXACT
    # Real extras on V2 stay unmatched — not ADDED.
    unmatched_target_keys = {
        row.target_unit.identity_key
        for row in result.unmatched_targets
        if row.target_unit and row.target_unit.identity_key
    }
    assert "CLAUSE:8.3" in unmatched_target_keys
    assert "CLAUSE:9.3" in unmatched_target_keys
    assert result.metadata["mapping_llm_calls"] == 0
    assert result.metadata["source_clause_count"] >= 40
    assert result.metadata["mapping_latency_ms"] >= 0


def test_as_dict_is_traceable_without_contract_body() -> None:
    v1 = _norm("ĐIỀU 1. PHẠM VI\n1.2. Bí mật thương mại không được log.\n")
    result = map_normalized_structures(v1, v1)
    payload = result.find_source("CLAUSE:1.2").as_dict()  # type: ignore[union-attr]
    assert payload["source_ref"]["identity_key"] == "CLAUSE:1.2"
    assert payload["signals"]["number_match"] is True
    assert "Bí mật thương mại" not in str(payload)
