# =============================================================================
# File: test_clause_normalization.py
# Module/Service: Clause Normalization (FR8 / TASK-CMP-02)
# Layer: Service
# Purpose: Unit/integration tests for canonical clause identity — no mapping.
# Responsibilities:
#   - Title/number/alias normalization with original text preserved
#   - V1/V2 Điều 1.2 and 1.3 share identity_key; body differences stay in text
#   - Idempotency; appendix ≠ article; 0 LLM
# Dependencies:
#   - pytest, extract_from_text/pages, normalize_structure, ClauseNormalizer
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: Does not assert V1↔V2 matches beyond identity keys.
# =============================================================================

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.ai.document_structure.normalization import (
    build_aliases,
    identity_key_for,
    normalize_structure,
    normalize_title,
)
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.types import StructuralUnitType
from app.models.documents import Document, DocumentVersion
from app.models.enums import ChunkLayoutType, DocumentVersionStatus, FileType
from app.repositories.retrieval import ChunkHydrationRow
from app.services.document_structure.extractor import DocumentStructureExtractor
from app.services.document_structure.normalizer import ClauseNormalizer

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
V1_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
V2_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"

BASIC = """\
ĐIỀU 1. PHẠM VI
1.1. Nội dung phạm vi một.
1.2. Nội dung phạm vi hai.
1.3. Nội dung phạm vi ba.

ĐIỀU 2. THỜI HẠN
2.1. Thời hạn mười hai tháng.

PHỤ LỤC 01 — Tiêu chí nghiệm thu
Chi tiết tiêu chí.
"""


def _pages_from_fixture_txt(path: Path) -> list[tuple[int, str]]:
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


def _normalize_text(text: str):
    structure = extract_from_text(text, title="HĐ")
    return ClauseNormalizer().normalize(structure)


@pytest.mark.parametrize(
    "title",
    [
        "PHẠM VI CÔNG VIỆC",
        "Phạm vi công việc",
        "Phạm  vi   công việc.",
        "phạm vi công việc",
    ],
)
def test_title_formatting_collapses_to_same_normalized_title(title: str) -> None:
    assert normalize_title(title) == normalize_title("PHẠM VI CÔNG VIỆC")


def test_dieu_1_2_aliases_include_language_variants() -> None:
    aliases = build_aliases(
        StructuralUnitType.CLAUSE,
        "1.2",
        parent_number="1",
        title="Chi tiết tính năng",
    )
    assert "1.2" in aliases
    assert "điều 1.2" in aliases
    assert "article 1.2" in aliases
    assert "khoản 1.2" in aliases
    assert "điều 1 khoản 2" in aliases
    assert "chi tiết tính năng" in aliases
    assert "dieu 1.2" in aliases


def test_identity_key_is_type_plus_canonical_number() -> None:
    assert identity_key_for(StructuralUnitType.ARTICLE, "01") == "ARTICLE:1"
    assert identity_key_for(StructuralUnitType.CLAUSE, "1.2.") == "CLAUSE:1.2"
    assert identity_key_for(StructuralUnitType.APPENDIX, "01") == "APPENDIX:01"
    assert identity_key_for(StructuralUnitType.DOCUMENT, "1") is None


def test_basic_contract_normalized_identity_and_paths() -> None:
    normalized = _normalize_text(BASIC)
    clause = normalized.find(StructuralUnitType.CLAUSE, "1.2")
    article = normalized.find(StructuralUnitType.ARTICLE, "1")
    appendix = normalized.find(StructuralUnitType.APPENDIX, "01")
    assert clause is not None
    assert article is not None
    assert appendix is not None
    assert clause.identity_key == "CLAUSE:1.2"
    assert clause.qualified_key == "ARTICLE:1/CLAUSE:1.2"
    assert clause.number_path == ("1", "1.2")
    assert clause.parent_identity_key == "ARTICLE:1"
    assert "Điều 1" in clause.heading_path
    assert "1.2" in clause.heading_path
    assert appendix.identity_key == "APPENDIX:01"
    assert appendix.identity_key != article.identity_key
    assert article.identity_key == "ARTICLE:1"


def test_original_text_and_title_are_not_rewritten() -> None:
    original = "ĐIỀU 1. PHẠM VI\n1.2. Nội dung phạm vi hai.\n"
    structure = extract_from_text(original)
    extracted = structure.find(StructuralUnitType.CLAUSE, "1.2")
    normalized = normalize_structure(structure).find(StructuralUnitType.CLAUSE, "1.2")
    assert extracted is not None and normalized is not None
    assert normalized.original_text == extracted.text
    assert normalized.original_title == extracted.title
    assert normalized.original_heading == extracted.original_heading
    assert "nội dung phạm vi hai" in normalized.normalized_body


def test_heading_variants_share_article_identity() -> None:
    keys = []
    for heading in ("ĐIỀU 1. PHẠM VI", "Điều 1.", "ARTICLE 1", "Điều 1:"):
        norm = _normalize_text(f"{heading}\n1.1. X.\n")
        article = norm.find(StructuralUnitType.ARTICLE, "1")
        assert article is not None
        keys.append(article.identity_key)
        assert article.original_heading is None or heading.split("\n")[0] in (
            article.original_heading or article.original_text
        )
    assert set(keys) == {"ARTICLE:1"}


def test_normalization_is_idempotent() -> None:
    structure = extract_from_text(BASIC)
    first = normalize_structure(structure)
    second = normalize_structure(structure)
    assert first.identity_keys() == second.identity_keys()
    for key, left in first.identity_index().items():
        right = second.identity_index()[key]
        assert left.aliases == right.aliases
        assert left.normalized_title == right.normalized_title
        assert left.normalized_body == right.normalized_body
        assert left.qualified_key == right.qualified_key
        assert left.original_text == right.original_text


def test_empty_and_gap_documents_normalize_without_crash() -> None:
    empty = _normalize_text("")
    assert empty.identity_keys() == set()
    gap = _normalize_text("ĐIỀU 1. MỘT\n1.1. A\n\nĐIỀU 3. BA\n3.1. C\n")
    assert gap.find(StructuralUnitType.ARTICLE, "1") is not None
    assert gap.find(StructuralUnitType.ARTICLE, "3") is not None
    assert gap.find(StructuralUnitType.ARTICLE, "2") is None
    assert gap.metadata["normalization_llm_calls"] == 0


def test_ocr_variant_still_receives_identity_key() -> None:
    norm = _normalize_text("DIEU 8.2\nĐIẺU 8\n")
    keys = norm.identity_keys()
    assert keys
    assert any(key.endswith(":8") or key.endswith(":8.2") for key in keys)
    ocr_units = [u for u in norm.walk() if u.identity_key]
    assert ocr_units
    assert all(u.original_text for u in ocr_units)


def test_v1_v2_clause_1_2_and_1_3_share_identity_keys() -> None:
    v1 = normalize_structure(
        extract_from_pages(_pages_from_fixture_txt(V1_TXT), title="V1")
    )
    v2 = normalize_structure(
        extract_from_pages(_pages_from_fixture_txt(V2_TXT), title="V2")
    )
    for number in ("1.2", "1.3"):
        left = v1.find(StructuralUnitType.CLAUSE, number)
        right = v2.find(StructuralUnitType.CLAUSE, number)
        assert left is not None and right is not None
        assert left.identity_key == right.identity_key == f"CLAUSE:{number}"
        assert left.qualified_key == right.qualified_key == f"ARTICLE:1/CLAUSE:{number}"
        assert left.aliases == right.aliases
        assert left.original_text
        assert right.original_text


def test_v1_v2_same_identity_keeps_divergent_original_bodies() -> None:
    """Normalization equalizes identity, not semantics.

    Điều 2.1 exists in both contracts with different duration wording.
    This task only asserts they share CLAUSE:2.1 — it does not classify
    the change as an addition/deletion or run comparison.
    """
    v1 = normalize_structure(
        extract_from_pages(_pages_from_fixture_txt(V1_TXT), title="V1")
    )
    v2 = normalize_structure(
        extract_from_pages(_pages_from_fixture_txt(V2_TXT), title="V2")
    )
    left = v1.find(StructuralUnitType.CLAUSE, "2.1")
    right = v2.find(StructuralUnitType.CLAUSE, "2.1")
    assert left is not None and right is not None
    assert left.identity_key == right.identity_key == "CLAUSE:2.1"
    assert left.original_text != right.original_text
    assert "06" in left.original_text
    assert "12" in right.original_text
    assert left.normalized_body != right.normalized_body


def test_normalization_does_not_drop_source_binding() -> None:
    v1 = normalize_structure(
        extract_from_pages(_pages_from_fixture_txt(V1_TXT), title="V1")
    )
    clause = v1.find(StructuralUnitType.CLAUSE, "1.2")
    assert clause is not None
    assert clause.page_start == 1
    assert clause.chunk_ids
    assert clause.source_spans


def test_no_llm_and_no_cross_document_mapping_api() -> None:
    normalized = _normalize_text(BASIC)
    assert normalized.metadata["normalization_llm_calls"] == 0
    assert not hasattr(ClauseNormalizer, "map")
    assert not hasattr(ClauseNormalizer, "compare")
    assert not hasattr(ClauseNormalizer, "match")


class _FakeDocuments:
    def __init__(self, document: Document, version: DocumentVersion) -> None:
        self.document = document
        self.version = version

    async def get_document(self, workspace_id: uuid.UUID, document_id: uuid.UUID):
        if document_id == self.document.id and workspace_id == self.document.workspace_id:
            return self.document
        return None

    async def get_version(self, workspace_id, document_id, version_id):
        if version_id == self.version.id and document_id == self.document.id:
            return self.version
        return None


class _FakeRetrieval:
    def __init__(self, rows: list[ChunkHydrationRow]) -> None:
        self.rows = rows
        self.top_k_calls = 0

    async def list_chunks_for_document(self, *args, **kwargs):
        return list(self.rows)

    async def list_top_chunks_by_topic(self, *args, **kwargs):
        self.top_k_calls += 1
        raise AssertionError("normalization must not use top-k retrieval")


@pytest.mark.asyncio
async def test_extract_normalized_uses_full_corpus_only() -> None:
    workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    document = Document(
        id=document_id,
        workspace_id=workspace_id,
        title="HĐ",
        file_type=FileType.pdf,
        current_version_id=version_id,
    )
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="x",
        file_size_bytes=1,
        checksum_sha256="a" * 64,
        status=DocumentVersionStatus.ready,
        is_current=True,
        page_count=1,
    )
    row = ChunkHydrationRow(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        document_version_id=version_id,
        workspace_id=workspace_id,
        content="ĐIỀU 1. PHẠM VI\n1.2. Có trong corpus.\n1.3. Cũng có.",
        title="HĐ",
        page_number=1,
        chunk_index=0,
        layout_type=ChunkLayoutType.paragraph,
    )
    retrieval = _FakeRetrieval([row])
    extractor = DocumentStructureExtractor(
        documents=_FakeDocuments(document, version),  # type: ignore[arg-type]
        retrieval=retrieval,  # type: ignore[arg-type]
    )
    raw = await extractor.extract(document_id, workspace_id=workspace_id)
    assert raw.find(StructuralUnitType.CLAUSE, "1.2") is not None

    normalized = await extractor.extract_normalized(document_id, workspace_id=workspace_id)
    assert retrieval.top_k_calls == 0
    clause = normalized.find(StructuralUnitType.CLAUSE, "1.2")
    assert clause is not None
    assert clause.identity_key == "CLAUSE:1.2"
    assert "normalization_duration_ms" in normalized.metadata
    assert normalized.metadata["normalization_llm_calls"] == 0
