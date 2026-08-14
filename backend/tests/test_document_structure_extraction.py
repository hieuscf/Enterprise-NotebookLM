# =============================================================================
# File: test_document_structure_extraction.py
# Module/Service: Document Structure Extraction (FR8 / TASK-CMP-01)
# Layer: Service
# Purpose: Unit, integration, and V1/V2 regression tests for structure extraction.
# Responsibilities:
#   - Article/clause/appendix hierarchy and numbering normalization
#   - Multi-page / multi-chunk source binding
#   - OCR noise must not crash; V1 and V2 both contain Điều 1.2 and 1.3
#   - Prove "not retrieved" is not treated as "does not exist"
# Dependencies:
#   - pytest, app.ai.document_structure, DocumentStructureExtractor
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; fixture PDFs/txt, no live Postgres)
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.pdf
# Important Notes: 0 LLM / 0 vector retrieval. Uses FULL corpus only.
# =============================================================================

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from app.ai.document_structure.pipeline import (
    added_canonical_keys,
    extract_from_pages,
    extract_from_text,
    extract_structure,
)
from app.ai.document_structure.types import (
    CorpusChunk,
    DocumentCorpus,
    DocumentStructure,
    ExtractionConfidence,
    StructuralUnit,
    StructuralUnitType,
)
from app.models.documents import Document, DocumentVersion
from app.models.enums import ChunkLayoutType, DocumentVersionStatus, FileType
from app.repositories.retrieval import ChunkHydrationRow
from app.services.document_structure.extractor import (
    DocumentStructureError,
    DocumentStructureExtractor,
)

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
V1_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
V2_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"
V1_PDF = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.pdf"
V2_PDF = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.pdf"

BASIC_CONTRACT = """\
ĐIỀU 1. PHẠM VI
1.1. Nội dung phạm vi một.
1.2. Nội dung phạm vi hai.
1.3. Nội dung phạm vi ba.

ĐIỀU 2. THỜI HẠN
2.1. Thời hạn mười hai tháng.
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


def _unit_numbers(structure: DocumentStructure, unit_type: StructuralUnitType) -> list[str]:
    return [
        unit.number
        for unit in structure.walk()
        if unit.type is unit_type and unit.number
    ]


def _child_numbers(parent: StructuralUnit) -> list[str]:
    return [child.number for child in parent.children if child.number]


# ---------------------------------------------------------------------------
# Test 1 — Basic contract
# ---------------------------------------------------------------------------


def test_basic_contract_article_clause_hierarchy() -> None:
    structure = extract_from_text(BASIC_CONTRACT, title="HĐ mẫu")
    assert _unit_numbers(structure, StructuralUnitType.ARTICLE) == ["1", "2"]
    article1 = structure.find(StructuralUnitType.ARTICLE, "1")
    article2 = structure.find(StructuralUnitType.ARTICLE, "2")
    assert article1 is not None
    assert article2 is not None
    assert _child_numbers(article1) == ["1.1", "1.2", "1.3"]
    assert _child_numbers(article2) == ["2.1"]
    for number in ("1.1", "1.2", "1.3"):
        clause = structure.find(StructuralUnitType.CLAUSE, number)
        assert clause is not None
        assert clause.parent_id == article1.id
    assert structure.find(StructuralUnitType.CLAUSE, "2.1") is not None
    assert "PHẠM VI" in (article1.title or article1.original_heading or "")
    assert "1.2. Nội dung phạm vi hai." in (structure.find(StructuralUnitType.CLAUSE, "1.2").text)


# ---------------------------------------------------------------------------
# Test 2 — Formatting variation / number normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "heading",
    [
        "ĐIỀU 1",
        "Điều 1.",
        "Điều 1:",
        "ARTICLE 1",
        "ĐIỀU 1. PHẠM VI CÔNG VIỆC",
        "# ĐIỀU 1. PHẠM VI",
    ],
)
def test_article_heading_formatting_normalizes_to_article_1(heading: str) -> None:
    text = f"{heading}\n1.1. Nội dung.\n"
    structure = extract_from_text(text)
    article = structure.find(StructuralUnitType.ARTICLE, "1")
    assert article is not None, f"failed to normalize {heading!r}"
    assert article.number == "1"
    assert article.type is StructuralUnitType.ARTICLE
    assert heading.strip("# ").split("\n")[0] in (article.original_heading or article.text)


def test_two_line_dieu_title_is_captured() -> None:
    text = "ĐIỀU 1\nPHẠM VI CÔNG VIỆC\n1.1. Nội dung.\n"
    structure = extract_from_text(text)
    article = structure.find(StructuralUnitType.ARTICLE, "1")
    assert article is not None
    assert "PHẠM VI CÔNG VIỆC" in article.title


# ---------------------------------------------------------------------------
# Test 3 — Appendix is not an article
# ---------------------------------------------------------------------------


def test_appendix_is_not_classified_as_article() -> None:
    text = """\
ĐIỀU 1. PHẠM VI
1.1. Xem phụ lục.

PHỤ LỤC 01 — Tiêu chí nghiệm thu
Chi tiết tiêu chí.
"""
    structure = extract_from_text(text)
    appendix = structure.find(StructuralUnitType.APPENDIX, "01")
    assert appendix is not None
    assert structure.find(StructuralUnitType.ARTICLE, "01") is None
    assert "01" not in _unit_numbers(structure, StructuralUnitType.ARTICLE)
    assert appendix.parent_id == structure.root.id if structure.root else appendix.parent_id


# ---------------------------------------------------------------------------
# Test 4 — Multi-page / multi-chunk clause
# ---------------------------------------------------------------------------


def test_multi_page_clause_binds_all_pages_and_chunk_ids() -> None:
    doc_id = uuid.uuid4()
    c0 = uuid.uuid4()
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()
    chunks = [
        CorpusChunk(
            chunk_id=c0,
            chunk_index=0,
            page_number=1,
            content="ĐIỀU 1. PHẠM VI\n1.1. Ngắn.",
        ),
        CorpusChunk(
            chunk_id=c1,
            chunk_index=1,
            page_number=2,
            content="1.2. Bắt đầu khoản dài trên trang 2.",
        ),
        CorpusChunk(
            chunk_id=c2,
            chunk_index=2,
            page_number=3,
            content="Phần còn lại của khoản 1.2 trên trang 3.\n1.3. Khoản tiếp theo.",
        ),
    ]
    structure = extract_structure(
        DocumentCorpus(document_id=doc_id, title="V", chunks=chunks)
    )
    clause = structure.find(StructuralUnitType.CLAUSE, "1.2")
    assert clause is not None
    assert clause.page_start == 2
    assert clause.page_end == 3
    assert set(clause.chunk_ids) == {c1, c2}
    assert "trang 2" in clause.text
    assert "trang 3" in clause.text
    assert "1.3. Khoản tiếp theo." not in clause.text
    next_clause = structure.find(StructuralUnitType.CLAUSE, "1.3")
    assert next_clause is not None
    assert next_clause.page_start == 3
    assert c2 in next_clause.chunk_ids


# ---------------------------------------------------------------------------
# Test 5 — OCR noise must not crash; low confidence when uncertain
# ---------------------------------------------------------------------------


def test_ocr_noise_does_not_crash_and_is_low_confidence() -> None:
    text = "DIEU 8.2\nĐIẺU 8\n1.1. Vẫn parse được.\n"
    structure = extract_from_text(text)
    units = [u for u in structure.walk() if u.type is not StructuralUnitType.DOCUMENT]
    assert structure.metadata.get("detection_llm_calls") == 0
    ocr_units = [
        u
        for u in units
        if u.detection_source == "ocr_variant" or u.confidence_label is ExtractionConfidence.LOW
    ]
    assert ocr_units, "OCR variants should be detected with LOW confidence, not crash"
    assert all(
        u.confidence_label is ExtractionConfidence.LOW
        or (u.confidence is not None and u.confidence < 0.6)
        for u in ocr_units
    )


def test_empty_and_malformed_documents_do_not_crash() -> None:
    empty = extract_from_text("")
    assert empty.sections == [] or empty.root is not None
    gap = extract_from_text("ĐIỀU 1. MỘT\n1.1. A\n\nĐIỀU 3. BA\n3.1. C\n")
    assert gap.find(StructuralUnitType.ARTICLE, "1") is not None
    assert gap.find(StructuralUnitType.ARTICLE, "3") is not None
    assert gap.find(StructuralUnitType.ARTICLE, "2") is None
    untitled = extract_from_text("ĐIỀU 1\n1.1. Có nội dung không tiêu đề.\n")
    assert untitled.find(StructuralUnitType.ARTICLE, "1") is not None


# ---------------------------------------------------------------------------
# Test 6 — Identical V1/V2 produce equivalent structure
# ---------------------------------------------------------------------------


def test_identical_contracts_produce_equivalent_structure() -> None:
    v1 = extract_from_text(BASIC_CONTRACT, title="V1")
    v2 = extract_from_text(BASIC_CONTRACT, title="V2")
    assert v1.canonical_keys() == v2.canonical_keys()
    for key, left in v1.canonical_index().items():
        right = v2.canonical_index()[key]
        assert left.type is right.type
        assert left.number == right.number
        assert left.title == right.title
        assert left.text == right.text
        assert _child_numbers(left) == _child_numbers(right)


def test_extract_is_idempotent_on_same_corpus() -> None:
    first = extract_from_text(BASIC_CONTRACT)
    second = extract_from_text(BASIC_CONTRACT)
    assert first.canonical_keys() == second.canonical_keys()
    assert [u.id for u in first.walk() if u.type is not StructuralUnitType.DOCUMENT] == [
        u.id for u in second.walk() if u.type is not StructuralUnitType.DOCUMENT
    ]


# ---------------------------------------------------------------------------
# Test 7 — Critical V1/V2 regression (Điều 1.2 / 1.3 exist in BOTH)
# ---------------------------------------------------------------------------


def test_v1_and_v2_both_contain_clause_1_2_and_1_3() -> None:
    v1 = extract_from_pages(_pages_from_fixture_txt(V1_TXT), title="HĐ V1")
    v2 = extract_from_pages(_pages_from_fixture_txt(V2_TXT), title="HĐ V2")

    for structure, label in ((v1, "V1"), (v2, "V2")):
        for number in ("1.2", "1.3"):
            clause = structure.find(StructuralUnitType.CLAUSE, number)
            assert clause is not None, f"{label} missing Điều/khoản {number}"
            assert clause.page_start == 1
            assert clause.text.strip()
        article = structure.find(StructuralUnitType.ARTICLE, "1")
        assert article is not None, f"{label} missing Điều 1"
        assert "1.2" in _child_numbers(article)
        assert "1.3" in _child_numbers(article)

    added = added_canonical_keys(v1, v2)
    assert "CLAUSE:1.2" not in added
    assert "CLAUSE:1.3" not in added
    assert "ARTICLE:1" not in added
    # Real V2 additions (8.3, 9.3) may appear; 1.2/1.3 must never look "added".
    assert v1.find(StructuralUnitType.APPENDIX, "01") is not None
    assert v2.find(StructuralUnitType.APPENDIX, "01") is not None


def test_full_corpus_extraction_not_top_k_prevents_false_added_clauses() -> None:
    """Retrieval that only sees V2 must not decide V1 lacks 1.2/1.3.

    Structure extraction always reads the full ingested corpus, so both
    versions still report CLAUSE 1.2 and 1.3.
    """
    v1_pages = _pages_from_fixture_txt(V1_TXT)
    v2_pages = _pages_from_fixture_txt(V2_TXT)
    v1_full = extract_from_pages(v1_pages, title="V1-full")
    v2_full = extract_from_pages(v2_pages, title="V2-full")

    # Simulate a buggy comparison context: V1 top-k omitted 1.2/1.3.
    v1_topk_text = v1_pages[0][1].split("1.2.")[0]
    v1_topk = extract_from_text(v1_topk_text, title="V1-topk")
    buggy_added = added_canonical_keys(v1_topk, v2_full)
    assert "CLAUSE:1.2" in buggy_added or v1_topk.find(StructuralUnitType.CLAUSE, "1.2") is None

    correct_added = added_canonical_keys(v1_full, v2_full)
    assert v1_full.find(StructuralUnitType.CLAUSE, "1.2") is not None
    assert v1_full.find(StructuralUnitType.CLAUSE, "1.3") is not None
    assert "CLAUSE:1.2" not in correct_added
    assert "CLAUSE:1.3" not in correct_added


def test_v1_v2_pdf_extraction_matches_txt_regression() -> None:
    pytest.importorskip("fitz")
    if not V1_PDF.exists() or not V2_PDF.exists():
        pytest.skip("V1/V2 PDF fixtures are not present")
    import fitz

    def pages(path: Path) -> list[tuple[int, str]]:
        doc = fitz.open(path)
        return [(index + 1, page.get_text()) for index, page in enumerate(doc)]

    v1 = extract_from_pages(pages(V1_PDF), title="PDF V1")
    v2 = extract_from_pages(pages(V2_PDF), title="PDF V2")
    for structure in (v1, v2):
        assert structure.find(StructuralUnitType.CLAUSE, "1.2") is not None
        assert structure.find(StructuralUnitType.CLAUSE, "1.3") is not None
        assert structure.find(StructuralUnitType.ARTICLE, "1") is not None
        assert structure.find(StructuralUnitType.APPENDIX, "01") is not None
    assert "CLAUSE:1.2" not in added_canonical_keys(v1, v2)
    assert "CLAUSE:1.3" not in added_canonical_keys(v1, v2)
    assert structure.metadata.get("detection_llm_calls") == 0


# ---------------------------------------------------------------------------
# Heading metadata / mixed language / original text preserved
# ---------------------------------------------------------------------------


def test_heading_chunks_and_original_text_preserved() -> None:
    heading_id = uuid.uuid4()
    body_id = uuid.uuid4()
    original = "ĐIỀU 1. PHẠM VI CÔNG VIỆC"
    chunks = [
        CorpusChunk(
            chunk_id=heading_id,
            chunk_index=0,
            page_number=1,
            content=original,
            layout_type=ChunkLayoutType.heading.value,
        ),
        CorpusChunk(
            chunk_id=body_id,
            chunk_index=1,
            page_number=1,
            content="1.1. Giữ nguyên câu gốc — Bên B thực hiện.\n1.2. Câu gốc thứ hai.",
            layout_type=ChunkLayoutType.paragraph.value,
        ),
    ]
    structure = extract_structure(
        DocumentCorpus(document_id=uuid.uuid4(), title="Doc", chunks=chunks)
    )
    article = structure.find(StructuralUnitType.ARTICLE, "1")
    assert article is not None
    assert original in (article.original_heading or "")
    assert original in article.text or original == article.original_heading
    clause = structure.find(StructuralUnitType.CLAUSE, "1.1")
    assert clause is not None
    assert "Giữ nguyên câu gốc — Bên B thực hiện." in clause.text
    assert heading_id in article.chunk_ids


def test_no_offsets_are_invented() -> None:
    structure = extract_from_text(BASIC_CONTRACT)
    for unit in structure.walk():
        for span in unit.source_spans:
            assert span.start_offset is None
            assert span.end_offset is None


def test_extraction_does_not_call_llm() -> None:
    structure = extract_from_text(BASIC_CONTRACT)
    assert structure.metadata["detection_llm_calls"] == 0
    assert structure.metadata["articles_detected"] == 2
    assert structure.metadata["clauses_detected"] == 4


# ---------------------------------------------------------------------------
# Integration: DocumentStructureExtractor uses FULL chunk list, not top-k
# ---------------------------------------------------------------------------


class _FakeDocuments:
    def __init__(self, document: Document, version: DocumentVersion) -> None:
        self.document = document
        self.version = version

    async def get_document(self, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        if document_id == self.document.id and workspace_id == self.document.workspace_id:
            return self.document
        return None

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion | None:
        if (
            workspace_id == self.document.workspace_id
            and document_id == self.document.id
            and version_id == self.version.id
        ):
            return self.version
        return None


class _FakeRetrieval:
    def __init__(self, rows: list[ChunkHydrationRow]) -> None:
        self.rows = rows
        self.list_all_calls = 0
        self.top_k_calls = 0

    async def list_chunks_for_document(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
    ) -> list[ChunkHydrationRow]:
        self.list_all_calls += 1
        return list(self.rows)

    async def list_top_chunks_by_topic(self, *args: Any, **kwargs: Any) -> list[ChunkHydrationRow]:
        self.top_k_calls += 1
        raise AssertionError("structure extraction must not use top-k retrieval")


def _hydration(
    *,
    content: str,
    index: int,
    document: Document,
    version: DocumentVersion,
    page: int | None = 1,
) -> ChunkHydrationRow:
    return ChunkHydrationRow(
        chunk_id=uuid.uuid4(),
        document_id=document.id,
        document_version_id=version.id,
        workspace_id=document.workspace_id,
        content=content,
        title=document.title,
        page_number=page,
        chunk_index=index,
        layout_type=ChunkLayoutType.paragraph,
    )


@pytest.mark.asyncio
async def test_extractor_reads_all_chunks_and_is_idempotent() -> None:
    workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    document = Document(
        id=document_id,
        workspace_id=workspace_id,
        title="HĐ V1",
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
        layout_metadata=None,
    )
    rows = [
        _hydration(content=part, index=i, document=document, version=version)
        for i, part in enumerate(
            [
                "ĐIỀU 1. PHẠM VI\n1.1. A",
                "1.2. B",
                "1.3. C\nĐIỀU 2. THỜI HẠN\n2.1. D",
            ]
        )
    ]
    retrieval = _FakeRetrieval(rows)
    extractor = DocumentStructureExtractor(
        documents=_FakeDocuments(document, version),  # type: ignore[arg-type]
        retrieval=retrieval,  # type: ignore[arg-type]
    )
    first = await extractor.extract(document_id, workspace_id=workspace_id)
    second = await extractor.extract(document_id, workspace_id=workspace_id)
    assert retrieval.list_all_calls == 2
    assert retrieval.top_k_calls == 0
    assert first.find(StructuralUnitType.CLAUSE, "1.2") is not None
    assert first.find(StructuralUnitType.CLAUSE, "1.3") is not None
    assert first.canonical_keys() == second.canonical_keys()
    assert first.metadata.get("detection_llm_calls") == 0
    assert "extraction_duration_ms" in first.metadata


@pytest.mark.asyncio
async def test_extractor_missing_document_raises() -> None:
    extractor = DocumentStructureExtractor(
        documents=_FakeDocuments(  # type: ignore[arg-type]
            Document(
                id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                title="x",
                file_type=FileType.pdf,
            ),
            DocumentVersion(
                id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                uploaded_by=uuid.uuid4(),
                version_number=1,
                storage_path="x",
                file_size_bytes=1,
                checksum_sha256="a" * 64,
                status=DocumentVersionStatus.ready,
                is_current=True,
            ),
        ),
        retrieval=_FakeRetrieval([]),  # type: ignore[arg-type]
    )
    with pytest.raises(DocumentStructureError) as exc:
        await extractor.extract(uuid.uuid4(), workspace_id=uuid.uuid4())
    assert exc.value.code == "not_found"
