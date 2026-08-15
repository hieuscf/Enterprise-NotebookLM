# =============================================================================
# File: test_semantic_clause_matching.py
# Module/Service: Semantic Clause Matching (FR8 / TASK-CMP-05)
# Layer: Service
# Purpose: Unit, integration, V1/V2, false-positive/negative semantic tests.
# Responsibilities:
#   - Exact mappings are never overridden
#   - Renumber / reword / move accepted when multi-signal gates pass
#   - Similar-but-different, title-only, type clash, sibling, margin → reject
# Dependencies:
#   - pytest, CMP-01/02/03/04, refine_mapping_semantically
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: 0 LLM. Semantic layer uses leftover clauses only, not RAG.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.ai.document_structure.diff_engine import diff_normalized_structures
from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.mapping_engine import map_normalized_structures
from app.ai.document_structure.mapping_types import (
    ClauseMapping,
    MappingCandidate,
    MappingResult,
    MappingSignals,
    MappingStatus,
    MappingType,
    clause_ref,
)
from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    NormalizedUnit,
    normalize_structure,
)
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.semantic_config import SemanticMatchConfig
from app.ai.document_structure.semantic_engine import (
    can_accept_semantic,
    combined_semantic_score,
    refine_mapping_semantically,
    types_compatible,
)
from app.ai.document_structure.semantic_text import EmbeddingCache, embedding_text
from app.ai.document_structure.types import StructuralUnitType
from app.services.document_structure.mapper import ClauseMappingEngine
from app.services.document_structure.semantic import ClauseSemanticMatcher

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
    identity_key: str | None = None,
) -> NormalizedUnit:
    key = identity_key or f"{unit_type.value}:{number}"
    parent_number = parent_key.split(":")[-1] if parent_key else None
    number_path = (parent_number, number) if parent_number else (number,)
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
        page_start=1,
        page_end=1,
    )


def _signals(**overrides: object) -> MappingSignals:
    values = dict(
        number_match=False,
        type_match=True,
        parent_match=True,
        title_similarity=0.8,
        lexical_similarity=0.5,
        semantic_similarity=0.9,
        structural_position=0.5,
        relative_number_match=False,
        method="semantic",
    )
    values.update(overrides)
    return MappingSignals(**values)  # type: ignore[arg-type]


def _row(
    source: NormalizedUnit | None,
    target: NormalizedUnit | None,
    *,
    status: MappingStatus,
    mapping_type: MappingType = MappingType.EXACT,
    confidence: float = 1.0,
    candidates: list[MappingCandidate] | None = None,
) -> ClauseMapping:
    return ClauseMapping(
        source_unit=source,
        target_unit=target,
        mapping_type=mapping_type,
        confidence=confidence,
        confidence_level=status,
        signals=_signals(),
        source_ref=clause_ref(source, version_id=None) if source else None,
        target_ref=clause_ref(target, version_id=None) if target else None,
        candidates=candidates or [],
    )


def _mapping(
    *rows: ClauseMapping,
    unmatched: tuple[ClauseMapping, ...] = (),
) -> MappingResult:
    source_id = next(
        (row.source_unit.document_id for row in rows if row.source_unit),
        uuid4(),
    )
    target_id = next(
        (
            row.target_unit.document_id
            for row in (*rows, *unmatched)
            if row.target_unit
        ),
        uuid4(),
    )
    return MappingResult(
        source_document_id=source_id,
        target_document_id=target_id,
        source_version_id=None,
        target_version_id=None,
        mappings=list(rows),
        unmatched_targets=list(unmatched),
        metadata={"mapping_llm_calls": 0},
    )


def _fixed_embed(pairs: dict[str, list[float]], dim: int = 4):
    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            hit = None
            for key, vector in pairs.items():
                if key.casefold() in text.casefold():
                    hit = vector
                    break
            out.append(list(hit) if hit is not None else [0.01] * dim)
        return out

    return embed


# ---------------------------------------------------------------------------
# Unit — gates and scoring
# ---------------------------------------------------------------------------


def test_types_compatible_rejects_article_vs_appendix() -> None:
    article = _unit(
        source_id="a",
        unit_type=StructuralUnitType.ARTICLE,
        number="8",
        title="Liability",
        body="cap",
    )
    appendix = _unit(
        source_id="x",
        unit_type=StructuralUnitType.APPENDIX,
        number="01",
        title="Schedule",
        body="cap",
        document_id=uuid4(),
    )
    assert types_compatible(article, article) is True
    assert types_compatible(article, appendix) is False


def test_title_only_is_not_accepted() -> None:
    signals = _signals(title_similarity=0.99, lexical_similarity=0.10, semantic_similarity=0.40)
    score = combined_semantic_score(signals, config=SemanticMatchConfig(), sibling_mismatch=False)
    assert (
        can_accept_semantic(
            max(score, 0.80),
            signals,
            margin=0.20,
            config=SemanticMatchConfig(),
            sibling_mismatch=False,
        )
        is False
    )


def test_sibling_mismatch_requires_strong_content() -> None:
    signals = _signals(
        title_similarity=0.40,
        lexical_similarity=0.40,
        semantic_similarity=0.92,
        parent_match=True,
    )
    cfg = SemanticMatchConfig()
    score = combined_semantic_score(signals, config=cfg, sibling_mismatch=True)
    assert can_accept_semantic(score, signals, margin=0.20, config=cfg, sibling_mismatch=True) is False


def test_close_margin_is_not_accepted() -> None:
    signals = _signals()
    cfg = SemanticMatchConfig()
    assert (
        can_accept_semantic(0.90, signals, margin=0.01, config=cfg, sibling_mismatch=False)
        is False
    )


def test_embedding_text_is_derived_and_truncated() -> None:
    unit = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.2",
        title="Bồi thường",
        body="x" * 2000,
        parent_key="ARTICLE:8",
    )
    text = embedding_text(unit, max_chars=80)
    assert len(text) <= 80
    assert unit.original_text == "x" * 2000


def test_cache_hits_same_model_and_rejects_other_version() -> None:
    cache = EmbeddingCache(model_name="m", model_version="v1")
    calls = {"n": 0}

    def embed(texts: list[str]) -> list[list[float]]:
        calls["n"] += 1
        return [[1.0, 0.0] for _ in texts]

    first = cache.get_or_embed(["hello"], embed)
    second = cache.get_or_embed(["hello"], embed)
    assert first == second
    assert calls["n"] == 1
    assert cache.hits == 1
    assert cache.compatible("m", "v2") is False


# ---------------------------------------------------------------------------
# Exact bypass + semantic accept / reject
# ---------------------------------------------------------------------------


def test_exact_mapping_is_not_overridden_ac04() -> None:
    source = _unit(
        source_id="v1-8.2",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.2",
        title="Cap",
        body="giới hạn 500 triệu",
        parent_key="ARTICLE:8",
    )
    exact_target = _unit(
        source_id="v2-8.2",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.2",
        title="Cap",
        body="giới hạn 100 triệu",
        parent_key="ARTICLE:8",
        document_id=uuid4(),
    )
    lure = _unit(
        source_id="v2-9.9",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.9",
        title="Cap",
        body="giới hạn bồi thường rất giống",
        parent_key="ARTICLE:9",
        document_id=exact_target.document_id,
    )
    mapping = _mapping(
        _row(source, exact_target, status=MappingStatus.EXACT),
        unmatched=(_row(None, lure, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(
        mapping,
        embed_fn=_fixed_embed({"500": [1.0, 0.0], "100": [0.2, 0.8], "rất giống": [1.0, 0.0]}),
    )
    row = refined.find_source("CLAUSE:8.2")
    assert row is not None
    assert row.accepted
    assert row.target_unit is exact_target
    assert row.confidence_level is MappingStatus.EXACT
    assert refined.metadata["semantic_accepted"] == 0


def test_renumbered_clause_is_accepted_ac01() -> None:
    source = _unit(
        source_id="v1-8",
        unit_type=StructuralUnitType.ARTICLE,
        number="8",
        title="Trách nhiệm và bồi thường",
        body="bên b chịu trách nhiệm bồi thường thiệt hại trực tiếp phát sinh từ vi phạm",
        identity_key="ARTICLE:8",
    )
    target = _unit(
        source_id="v2-9",
        unit_type=StructuralUnitType.ARTICLE,
        number="9",
        title="Trách nhiệm của bên b",
        body="bên b phải bồi thường các tổn thất trực tiếp do không thực hiện đúng nghĩa vụ",
        identity_key="ARTICLE:9",
        document_id=uuid4(),
    )
    mapping = _mapping(
        _row(source, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, target, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(
        mapping,
        embed_fn=_fixed_embed(
            {
                "trách nhiệm": [1.0, 0.1, 0.0, 0.0],
                "bên b": [1.0, 0.1, 0.0, 0.0],
            }
        ),
    )
    row = refined.find_source("ARTICLE:8")
    assert row is not None
    assert row.accepted
    assert row.target_unit is not None
    assert row.target_unit.identity_key == "ARTICLE:9"
    assert row.mapping_type is MappingType.SEMANTIC
    assert row.signals.semantic_similarity is not None
    assert row.signals.method.startswith("semantic")
    assert refined.metadata["semantic_llm_calls"] == 0


def test_reworded_clause_maps_semantically_ac02() -> None:
    source = _unit(
        source_id="v1-c",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.1",
        title="Bồi thường",
        body="bên b chịu trách nhiệm đối với mọi thiệt hại trực tiếp phát sinh từ hành vi vi phạm nghĩa vụ của mình",
        parent_key="ARTICLE:8",
    )
    target = _unit(
        source_id="v2-c",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.1",
        title="Bồi thường",
        body="bên b phải bồi thường các tổn thất trực tiếp do việc không thực hiện đúng các nghĩa vụ theo hợp đồng gây ra",
        parent_key="ARTICLE:9",
        identity_key="CLAUSE:9.1",
        document_id=uuid4(),
    )
    mapping = _mapping(
        _row(source, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, target, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(
        mapping,
        embed_fn=_fixed_embed(
            {
                "thiệt hại trực tiếp": [1.0, 0.05, 0.0, 0.0],
                "tổn thất trực tiếp": [0.98, 0.08, 0.0, 0.0],
                "nghĩa vụ": [1.0, 0.05, 0.0, 0.0],
            }
        ),
    )
    row = refined.find_source("CLAUSE:8.1")
    assert row is not None
    assert row.accepted
    assert row.mapping_type is MappingType.SEMANTIC
    assert row.target_unit is not None
    assert row.target_unit.identity_key == "CLAUSE:9.1"


def test_similar_but_different_purpose_is_rejected_ac03() -> None:
    source = _unit(
        source_id="pay",
        unit_type=StructuralUnitType.CLAUSE,
        number="3.1",
        title="Payment terms",
        body="bên a thanh toán 40 phần trăm trong vòng năm ngày làm việc kể từ ngày ký",
        parent_key="ARTICLE:3",
    )
    target = _unit(
        source_id="late",
        unit_type=StructuralUnitType.CLAUSE,
        number="3.4",
        title="Late payment penalty",
        body="nếu bên a chậm thanh toán thì phải chịu lãi phạt chậm trả theo lãi suất ngân hàng",
        parent_key="ARTICLE:3",
        document_id=uuid4(),
    )
    mapping = _mapping(
        _row(source, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, target, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(
        mapping,
        embed_fn=_fixed_embed(
            {"thanh toán": [0.95, 0.2, 0.0, 0.0], "chậm": [0.93, 0.25, 0.0, 0.0]}
        ),
    )
    row = refined.find_source("CLAUSE:3.1")
    assert row is not None
    assert row.accepted is False
    assert row.confidence_level in {MappingStatus.UNMATCHED, MappingStatus.LOW_CONFIDENCE, MappingStatus.AMBIGUOUS}


def test_high_similarity_amount_change_is_same_identity() -> None:
    source = _unit(
        source_id="cap1",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.2",
        title="Giới hạn bồi thường",
        body="tổng trách nhiệm bồi thường không vượt quá 500.000.000 đồng",
        parent_key="ARTICLE:8",
    )
    target = _unit(
        source_id="cap2",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.2",
        title="Giới hạn bồi thường",
        body="tổng trách nhiệm bồi thường không vượt quá 100.000.000 đồng",
        parent_key="ARTICLE:9",
        identity_key="CLAUSE:9.2",
        document_id=uuid4(),
    )
    mapping = _mapping(
        _row(source, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, target, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(mapping)
    row = refined.find_source("CLAUSE:8.2")
    assert row is not None and row.accepted
    v1 = NormalizedDocumentStructure(document_id=source.document_id, title="V1", sections=[source])
    v2 = NormalizedDocumentStructure(document_id=target.document_id, title="V2", sections=[target])
    diff = diff_normalized_structures(v1, v2, mapping=refined, refine_semantic=False)
    assert diff.find_source("CLAUSE:8.2").classification is DiffClassification.MODIFIED  # type: ignore[union-attr]


def test_ambiguous_close_candidates_ac05() -> None:
    source = _unit(
        source_id="a",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.2",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp và hợp lý",
        parent_key="ARTICLE:8",
    )
    x = _unit(
        source_id="x",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.2",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp và hợp lý phát sinh",
        parent_key="ARTICLE:9",
        document_id=uuid4(),
    )
    y = _unit(
        source_id="y",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.3",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp và hợp lý phát sinh",
        parent_key="ARTICLE:9",
        document_id=x.document_id,
    )
    mapping = _mapping(
        _row(source, None, status=MappingStatus.UNMATCHED),
        unmatched=(
            _row(None, x, status=MappingStatus.UNMATCHED),
            _row(None, y, status=MappingStatus.UNMATCHED),
        ),
    )
    refined = refine_mapping_semantically(
        mapping,
        embed_fn=_fixed_embed(
            {
                "8.2": [1.0, 0.0, 0.0, 0.0],
                "9.2": [0.99, 0.01, 0.0, 0.0],
                "9.3": [0.985, 0.02, 0.0, 0.0],
            }
        ),
        config=SemanticMatchConfig(min_margin=0.08, accept_min=0.60),
    )
    row = refined.find_source("CLAUSE:8.2")
    assert row is not None
    assert row.confidence_level is MappingStatus.AMBIGUOUS
    assert row.target_unit is None
    assert len(row.candidates) >= 2


def test_one_to_one_does_not_reuse_target_ac06() -> None:
    a = _unit(
        source_id="a",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="điều khoản thanh toán giá trị hợp đồng 40 phần trăm",
        parent_key="ARTICLE:1",
    )
    b = _unit(
        source_id="b",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.2",
        title="B",
        body="điều khoản khác hoàn toàn về bảo mật thông tin khách hàng",
        parent_key="ARTICLE:1",
        document_id=a.document_id,
    )
    x = _unit(
        source_id="x",
        unit_type=StructuralUnitType.CLAUSE,
        number="2.1",
        title="A",
        body="điều khoản thanh toán giá trị hợp đồng 40 phần trăm",
        parent_key="ARTICLE:2",
        document_id=uuid4(),
    )
    mapping = _mapping(
        _row(a, None, status=MappingStatus.UNMATCHED),
        _row(b, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, x, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(mapping)
    accepted_targets = [
        row.target_unit.identity_key
        for row in refined.accepted()
        if row.target_unit and row.target_unit.identity_key
    ]
    assert len(accepted_targets) == len(set(accepted_targets))
    assert refined.find_source("CLAUSE:1.1") is not None
    assert refined.find_source("CLAUSE:1.1").accepted  # type: ignore[union-attr]
    assert refined.find_source("CLAUSE:1.2").accepted is False  # type: ignore[union-attr]


def test_incompatible_type_is_not_a_candidate() -> None:
    source = _unit(
        source_id="art",
        unit_type=StructuralUnitType.ARTICLE,
        number="8",
        title="Liability",
        body="bồi thường thiệt hại trực tiếp",
    )
    appendix = _unit(
        source_id="apx",
        unit_type=StructuralUnitType.APPENDIX,
        number="01",
        title="Liability schedule",
        body="bồi thường thiệt hại trực tiếp chi tiết",
        document_id=uuid4(),
    )
    mapping = _mapping(
        _row(source, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, appendix, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(
        mapping,
        embed_fn=_fixed_embed({"bồi thường": [1.0, 0.0, 0.0, 0.0]}),
    )
    row = refined.find_source("ARTICLE:8")
    assert row is not None
    assert row.accepted is False


def test_embedding_failure_keeps_deterministic_rows() -> None:
    source = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="nội dung",
    )
    exact = _unit(
        source_id="t",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="nội dung",
        document_id=uuid4(),
    )
    leftover = _unit(
        source_id="u",
        unit_type=StructuralUnitType.CLAUSE,
        number="2.1",
        title="B",
        body="khác",
        document_id=source.document_id,
    )
    open_t = _unit(
        source_id="v",
        unit_type=StructuralUnitType.CLAUSE,
        number="2.1",
        title="B",
        body="khác",
        document_id=exact.document_id,
    )

    def boom(_texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embed down")

    mapping = _mapping(
        _row(source, exact, status=MappingStatus.EXACT),
        _row(leftover, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, open_t, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(mapping, embed_fn=boom)
    assert refined.find_source("CLAUSE:1.1").accepted  # type: ignore[union-attr]
    assert refined.metadata["semantic_fallback_count"] == 1
    assert refined.find_source("CLAUSE:2.1").confidence_level is MappingStatus.UNMATCHED  # type: ignore[union-attr]


def test_reranker_failure_still_uses_other_signals() -> None:
    source = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.1",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp phát sinh từ vi phạm nghĩa vụ",
        parent_key="ARTICLE:8",
    )
    target = _unit(
        source_id="t",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.1",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp phát sinh từ vi phạm nghĩa vụ",
        parent_key="ARTICLE:9",
        identity_key="CLAUSE:9.1",
        document_id=uuid4(),
    )

    def boom(_left: str, _right: str) -> float:
        raise RuntimeError("rerank down")

    mapping = _mapping(
        _row(source, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, target, status=MappingStatus.UNMATCHED),),
    )
    refined = refine_mapping_semantically(
        mapping,
        rerank_fn=boom,
        config=SemanticMatchConfig(enable_reranker=True),
    )
    row = refined.find_source("CLAUSE:8.1")
    assert row is not None
    assert row.accepted
    assert row.signals.reranker_score is None


def test_determinism_ac09() -> None:
    source = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.1",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp",
        parent_key="ARTICLE:8",
    )
    target = _unit(
        source_id="t",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.1",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp",
        parent_key="ARTICLE:9",
        identity_key="CLAUSE:9.1",
        document_id=uuid4(),
    )
    mapping = _mapping(
        _row(source, None, status=MappingStatus.UNMATCHED),
        unmatched=(_row(None, target, status=MappingStatus.UNMATCHED),),
    )
    first = refine_mapping_semantically(mapping).as_dict()
    second = refine_mapping_semantically(mapping).as_dict()
    first["metadata"].pop("semantic_latency_ms", None)
    second["metadata"].pop("semantic_latency_ms", None)
    assert first == second


def test_no_llm_and_no_raw_body_in_dict() -> None:
    source = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="bí mật thương mại không được log",
    )
    mapping = _mapping(_row(source, None, status=MappingStatus.UNMATCHED))
    refined = refine_mapping_semantically(mapping)
    dumped = refined.as_dict()
    assert refined.metadata["semantic_llm_calls"] == 0
    assert "bí mật thương mại" not in str(dumped["mappings"])


# ---------------------------------------------------------------------------
# Integration + regression
# ---------------------------------------------------------------------------


def test_pipeline_does_not_depend_on_retrieval_ac07() -> None:
    v1 = _norm(
        "ĐIỀU 8. TRÁCH NHIỆM VÀ BỒI THƯỜNG\n"
        "8.1. Bên B chịu trách nhiệm đối với mọi thiệt hại trực tiếp phát sinh từ vi phạm nghĩa vụ.\n"
    )
    v2 = _norm(
        "ĐIỀU 9. TRÁCH NHIỆM CỦA BÊN B\n"
        "9.1. Bên B phải bồi thường các tổn thất trực tiếp do không thực hiện đúng nghĩa vụ.\n"
    )
    mapping = ClauseMappingEngine().map_structures(
        v1,
        v2,
        embed_fn=_fixed_embed(
            {
                "thiệt hại trực tiếp": [1.0, 0.0, 0.1, 0.0],
                "tổn thất trực tiếp": [0.97, 0.05, 0.1, 0.0],
                "trách nhiệm": [1.0, 0.0, 0.1, 0.0],
            }
        ),
    )
    assert mapping.find_source("ARTICLE:8") is not None
    assert mapping.find_source("ARTICLE:8").accepted  # type: ignore[union-attr]
    assert mapping.find_source("CLAUSE:8.1").accepted  # type: ignore[union-attr]
    assert mapping.metadata["mapping_llm_calls"] == 0
    assert mapping.metadata.get("semantic_llm_calls", 0) == 0


def test_v1_v2_exact_pairs_stay_and_extras_unmatched() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    deterministic = map_normalized_structures(v1, v2)
    refined = ClauseSemanticMatcher().refine(deterministic)
    for key in ("CLAUSE:1.2", "CLAUSE:1.3", "ARTICLE:2", "ARTICLE:3", "ARTICLE:8", "ARTICLE:9", "ARTICLE:11"):
        before = deterministic.find_source(key)
        after = refined.find_source(key)
        assert before is not None and after is not None
        assert before.accepted and after.accepted
        assert after.target_unit is not None
        assert after.target_unit.identity_key == key
        assert after.confidence_level is MappingStatus.EXACT
    unmatched = {
        row.target_unit.identity_key
        for row in refined.unmatched_targets
        if row.target_unit and row.target_unit.identity_key
    }
    assert "CLAUSE:8.3" in unmatched
    assert "CLAUSE:9.3" in unmatched
    assert refined.metadata.get("semantic_accepted", 0) == 0
    assert refined.metadata["semantic_llm_calls"] == 0


def test_v1_v2_diff_after_semantic_keeps_1_2_unchanged() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    result = diff_normalized_structures(v1, v2)
    assert result.find_source("CLAUSE:1.2").classification is DiffClassification.UNCHANGED  # type: ignore[union-attr]
    assert result.find_source("CLAUSE:1.3").classification is DiffClassification.UNCHANGED  # type: ignore[union-attr]
    assert result.find_target("CLAUSE:8.3").classification is DiffClassification.ADDED  # type: ignore[union-attr]
    assert result.metadata["diff_llm_calls"] == 0
