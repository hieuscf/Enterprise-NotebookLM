# =============================================================================
# File: test_report_export.py
# Module/Service: Report Service (TASK-CMP-26)
# Layer: Service
# Purpose: Unit + service tests for secure Comparison Report export delivery.
# Responsibilities:
#   - Filename sanitization, MIME/extension mapping, Content-Disposition
#   - Status / format / missing-artifact / path-injection handling
#   - V1/V2 builder artifact is delivered unchanged (0 LLM)
# Dependencies:
#   - pytest, report.export helpers, ReportService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes)
# Related Modules: app.services.report.export, app.services.report_service
# Important Notes: Export must not regenerate comparison or call an LLM.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models.artifacts import Report
from app.models.enums import ReportFormat, ReportSourceType, ReportStatus
from app.repositories.reports import ReportItemSpec, ReportWithItems
from app.services.report.comparison_report_builder import build_comparison_report_content
from app.services.report.export import (
    artifact_key_is_owned,
    content_disposition_attachment,
    export_content_type,
    export_extension,
    resolve_export_format,
    sanitize_export_filename,
)
from app.services.report_service import ReportService, ReportServiceError
from app.services.renderers.common import build_report_object_key
from tests.test_reports_api import (
    FakeAggregation,
    FakeReportRepo,
    FakeSession,
    FakeStorage,
    _mock_docx_render,
    _mock_markdown_render,
    _mock_pdf_render,
)


def test_resolve_export_format_accepts_known_values() -> None:
    assert resolve_export_format(ReportFormat.pdf) is ReportFormat.pdf
    assert resolve_export_format("docx") is ReportFormat.docx
    assert resolve_export_format("markdown") is ReportFormat.markdown
    assert resolve_export_format("rtf") is None
    assert resolve_export_format(None) is None


def test_mime_and_extension_mapping() -> None:
    assert export_extension(ReportFormat.pdf) == "pdf"
    assert export_extension(ReportFormat.docx) == "docx"
    assert export_extension(ReportFormat.markdown) == "md"
    assert export_content_type(ReportFormat.pdf) == "application/pdf"
    assert export_content_type(ReportFormat.docx).startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert export_content_type(ReportFormat.markdown).startswith("text/markdown")


def test_sanitize_filename_strips_path_traversal() -> None:
    name = sanitize_export_filename("../../secret", ReportFormat.pdf)
    assert name.endswith(".pdf")
    assert ".." not in name
    assert "/" not in name
    assert "\\" not in name


def test_sanitize_filename_strips_reserved_characters() -> None:
    name = sanitize_export_filename('Contract Comparison: V1/V2*?<>|"', ReportFormat.docx)
    assert name.endswith(".docx")
    assert all(ch not in name for ch in '\\/:*?"<>|')


def test_sanitize_filename_unicode_keeps_letters() -> None:
    name = sanitize_export_filename("Hợp đồng mẫu", ReportFormat.markdown)
    assert name.endswith(".md")
    assert "Hợp" in name or "dong" in name.lower() or name.startswith("report") is False


def test_content_disposition_has_ascii_and_utf8_filename() -> None:
    filename = sanitize_export_filename("Hợp đồng V1/V2", ReportFormat.pdf)
    header = content_disposition_attachment(filename)
    assert header.startswith("attachment;")
    assert 'filename="' in header
    assert "filename*=UTF-8''" in header
    assert ".." not in header
    assert "\n" not in header


def test_artifact_key_must_match_workspace_and_report() -> None:
    workspace_id = uuid.uuid4()
    report_id = uuid.uuid4()
    key = f"workspaces/{workspace_id}/reports/{report_id}/report.pdf"
    assert artifact_key_is_owned(key, workspace_id=workspace_id, report_id=report_id)
    assert not artifact_key_is_owned(
        key, workspace_id=uuid.uuid4(), report_id=report_id
    )
    assert not artifact_key_is_owned(
        "s3://bucket/internal/report.pdf",
        workspace_id=workspace_id,
        report_id=report_id,
    )
    assert not artifact_key_is_owned(
        f"workspaces/{workspace_id}/reports/{report_id}/../secret.pdf",
        workspace_id=workspace_id,
        report_id=report_id,
    )
    assert not artifact_key_is_owned(
        "/minio/internal/report.pdf",
        workspace_id=workspace_id,
        report_id=report_id,
    )
    assert not artifact_key_is_owned(None, workspace_id=workspace_id, report_id=report_id)


def _service(
    reports: FakeReportRepo,
    storage: FakeStorage,
    aggregation: FakeAggregation,
    staging_dir: Path,
) -> ReportService:
    return ReportService(
        session=FakeSession(),  # type: ignore[arg-type]
        reports=reports,  # type: ignore[arg-type]
        aggregation=aggregation,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        enqueue=False,
        markdown_render_fn=_mock_markdown_render,
        docx_render_fn=_mock_docx_render,
        pdf_render_fn=_mock_pdf_render,
        staging_dir=staging_dir,
    )


@pytest.mark.asyncio
async def test_export_pending_is_not_ready(tmp_path: Path) -> None:
    workspace_id = uuid.uuid4()
    source_id = uuid.uuid4()
    reports = FakeReportRepo()
    created = await reports.create_pending(
        workspace_id=workspace_id,
        created_by=uuid.uuid4(),
        title="Pending",
        format_=ReportFormat.pdf,
        items=[
            ReportItemSpec(
                source_type=ReportSourceType.summary,
                source_id=source_id,
                order_index=0,
            )
        ],
    )
    service = _service(reports, FakeStorage(), FakeAggregation(), tmp_path)
    with pytest.raises(ReportServiceError) as exc_info:
        await service.export_report(
            workspace_id=workspace_id,
            report_id=created.report.id,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "not_ready"


@pytest.mark.asyncio
async def test_export_does_not_regenerate(tmp_path: Path) -> None:
    workspace_id = uuid.uuid4()
    source_id = uuid.uuid4()
    reports = FakeReportRepo()
    storage = FakeStorage()
    aggregation = FakeAggregation()
    aggregation.allowed.add(source_id)
    created = await reports.create_pending(
        workspace_id=workspace_id,
        created_by=uuid.uuid4(),
        title="Ready",
        format_=ReportFormat.markdown,
        items=[
            ReportItemSpec(
                source_type=ReportSourceType.summary,
                source_id=source_id,
                order_index=0,
            )
        ],
    )
    service = _service(reports, storage, aggregation, tmp_path)
    ready = await service.process_report(created.report.id)
    assert ready is not None
    first_key = ready.file_path
    assert first_key is not None
    original = storage.objects[first_key]
    payload = await service.export_report(
        workspace_id=workspace_id,
        report_id=created.report.id,
    )
    exported = b"".join(payload.iterator)
    assert exported == original
    assert list(storage.objects.keys()) == [first_key]


@pytest.mark.asyncio
async def test_v1_v2_export_delivers_builder_markdown(tmp_path: Path) -> None:
    workspace_id = uuid.uuid4()
    report_id = uuid.uuid4()
    content = build_comparison_report_content(
        result={
            "similarities": [],
            "differences": [],
            "contract_comparison": {
                "summary": {
                    "total_clauses": 12,
                    "unchanged": 8,
                    "modified": 4,
                    "added": 2,
                    "removed": 0,
                },
                "clauses": {
                    "modified": [
                        {
                            "clause_id": "CLAUSE:8.2",
                            "status": "MODIFIED",
                            "risk": {"risk_level": "CRITICAL"},
                        }
                    ],
                    "added": [{"clause_id": "CLAUSE:8.3", "status": "ADDED"}],
                    "removed": [],
                    "unchanged": [{"clause_id": "CLAUSE:1.2", "status": "UNCHANGED"}],
                    "unresolved": [],
                },
            },
        },
        title="Hop_dong_mau_Ra_soat_Phap_ly",
        status="completed",
    )
    report = content["comparison_report"]
    assert report["changed_clauses"][0]["clause_id"] == "CLAUSE:8.2"
    assert report["added_clauses"][0]["clause_id"] == "CLAUSE:8.3"
    unchanged_ids = set(report["unchanged_clauses"]["clause_ids"])
    assert "CLAUSE:1.2" in unchanged_ids
    assert "CLAUSE:1.2" not in {row["clause_id"] for row in report["added_clauses"]}

    object_key = build_report_object_key(
        workspace_id=workspace_id,
        report_id=report_id,
        filename="Hop_dong_mau_Ra_soat_Phap_ly.md",
    )
    markdown = (
        "# Hop_dong_mau_Ra_soat_Phap_ly\n\n"
        "### Changed Clauses\n\n- 8.2\n\n"
        "### Added Clauses\n\n- 8.3\n"
    ).encode("utf-8")
    storage = FakeStorage()
    storage.objects[object_key] = markdown
    reports = FakeReportRepo()
    report = Report(
        id=report_id,
        workspace_id=workspace_id,
        created_by=uuid.uuid4(),
        title="Hop_dong_mau_Ra_soat_Phap_ly",
        format=ReportFormat.markdown,
        status=ReportStatus.ready,
        file_path=object_key,
        created_at=datetime.now(UTC),
    )
    reports.rows[report_id] = ReportWithItems(report=report, items=[])
    service = _service(reports, storage, FakeAggregation(), tmp_path)
    payload = await service.export_report(
        workspace_id=workspace_id,
        report_id=report_id,
    )
    body = b"".join(payload.iterator).decode("utf-8")
    assert payload.content_type.startswith("text/markdown")
    assert payload.filename.endswith(".md")
    assert "8.2" in body
    added = body.split("### Added Clauses", 1)[1].split("###", 1)[0]
    assert "8.3" in added
    assert "1.2" not in added
