# =============================================================================
# File: test_comparison_report_regression.py
# Module/Service: Report Service (TASK-CMP-24)
# Layer: Service
# Purpose: V1/V2 regression for comparison report generation.
# Responsibilities:
#   - Render stored Hop_dong_mau comparison output without remapping
#   - Reject false ADDED/REMOVED for Điều 1.2 / 1.3
#   - Export Markdown, DOCX, and PDF from the same builder model
# Dependencies:
#   - ContractComparisonOrchestrator, comparison_report_builder, renderers
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: 0 LLM calls. Upstream classification is authoritative.
# =============================================================================

from __future__ import annotations

import uuid
from pathlib import Path

import fitz
from docx import Document

from app.ai.document_structure.normalization import normalize_structure
from app.ai.document_structure.pipeline import extract_from_pages
from app.models.enums import ReportSourceType
from app.services.document_structure.orchestrator import ContractComparisonOrchestrator
from app.services.report.comparison_report_builder import (
    CONSERVATIVE_ABSENCE_MESSAGE,
    build_comparison_report_content,
)
from app.services.report_aggregation import AggregatedReportBlock
from app.services.renderers.docx_renderer import render_docx
from app.services.renderers.markdown_renderer import render_markdown
from app.services.renderers.pdf_renderer import render_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
V1_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
V2_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"

EXPECTED_MODIFIED = (
    "CLAUSE:2.1",
    "CLAUSE:3.1",
    "CLAUSE:8.2",
    "CLAUSE:11.2",
)
FORBIDDEN_ADDED = ("CLAUSE:1.2", "CLAUSE:1.3")
EXPECTED_ADDED = ("CLAUSE:8.3", "CLAUSE:9.3")


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


def _stored_result() -> dict:
    v1 = normalize_structure(
        extract_from_pages(_pages(V1_TXT), title="Hop dong V1")
    )
    v2 = normalize_structure(
        extract_from_pages(_pages(V2_TXT), title="Hop dong V2")
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    inner = report.as_dict(include_text=True)["comparison"]
    return {
        "similarities": [],
        "differences": [],
        "contract_comparison": inner,
    }


def test_v1_v2_report_preserves_upstream_classification(tmp_path: Path) -> None:
    stored = _stored_result()
    content = build_comparison_report_content(
        result=stored,
        title="Hop dong mau",
        status="completed",
    )
    report = content["comparison_report"]
    assert report is not None
    assert content["has_contract_report"] is True
    assert report["generation_metadata"]["llm_calls_report"] == 0

    changed_ids = {row["clause_id"] for row in report["changed_clauses"]}
    added_ids = {row["clause_id"] for row in report["added_clauses"]}
    removed_ids = {row["clause_id"] for row in report["removed_clauses"]}
    unchanged_ids = set(report["unchanged_clauses"]["clause_ids"])

    for key in EXPECTED_MODIFIED:
        assert key in changed_ids, key
        assert key not in added_ids
        assert key not in removed_ids
    for key in EXPECTED_ADDED:
        assert key in added_ids, key
    for key in FORBIDDEN_ADDED:
        assert key not in added_ids
        assert key not in removed_ids
        assert key in unchanged_ids

    block = AggregatedReportBlock(
        order_index=0,
        source_type=ReportSourceType.comparison,
        title="Hop dong mau",
        content=content,
    )
    report_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    kwargs = {
        "report_title": "Hop dong mau",
        "report_id": report_id,
        "workspace_id": workspace_id,
        "output_dir": tmp_path,
    }
    md = render_markdown([block], **kwargs)
    docx = render_docx([block], **kwargs)
    pdf = render_pdf(md.markdown, **kwargs)

    assert md.local_path.is_file() and md.local_path.stat().st_size > 0
    assert docx.local_path.is_file() and docx.local_path.stat().st_size > 0
    assert pdf.local_path.is_file() and pdf.local_path.stat().st_size > 0

    added_section = md.markdown.split("### Added Clauses", 1)[1].split("###", 1)[0]
    for key in FORBIDDEN_ADDED:
        assert display_not_added(added_section, key), key
    assert "8.3" in added_section
    assert "V1 không có điều khoản" not in md.markdown
    assert "Executive Summary" in md.markdown
    assert "8.2" in md.markdown

    document = Document(str(docx.local_path))
    docx_text = "\n".join(p.text for p in document.paragraphs)
    assert "Executive Summary" in docx_text
    assert "8.2" in docx_text

    with fitz.open(str(pdf.local_path)) as doc:
        pdf_text = "\n".join(page.get_text() for page in doc)
    assert "Executive Summary" in pdf_text
    assert "8.2" in pdf_text


def display_not_added(added_section: str, clause_id: str) -> bool:
    display = clause_id.split(":", 1)[-1]
    return display not in added_section


def test_builder_does_not_invent_absence_from_empty_evidence() -> None:
    content = build_comparison_report_content(
        result={
            "similarities": [],
            "differences": [],
            "contract_comparison": {
                "clauses": {
                    "added": [
                        {
                            "clause_id": "CLAUSE:8.3",
                            "status": "ADDED",
                            "v2_text": "New limitation",
                            "evidence": [],
                        }
                    ],
                    "modified": [],
                    "removed": [],
                    "unchanged": [],
                    "unresolved": [],
                }
            },
        }
    )
    added = content["comparison_report"]["detailed_clause_comparisons"][0]
    assert added["absence_note"] == CONSERVATIVE_ABSENCE_MESSAGE
    assert "V1 không có điều khoản" not in (added["absence_note"] or "")
