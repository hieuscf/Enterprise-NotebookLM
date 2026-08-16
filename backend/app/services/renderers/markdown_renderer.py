# =============================================================================
# File: markdown_renderer.py
# Module/Service: Report Service (FR9) — Markdown Renderer
# Layer: Service
# Purpose: Render AggregatedReportBlock list into a Markdown file (UC8).
# Responsibilities:
#   - One ``## {title}`` section per block (order preserved as given)
#   - Source-type-specific body: summary/comparison text+bullets; extraction
#     Markdown table or JSON fence; chat_session dialogue lines
#   - Write ``{title}_{report_id}.md`` under report staging path / MinIO key
# Dependencies:
#   - report_aggregation.AggregatedReportBlock; renderers.common
# Public Exports:
#   - render_markdown, MarkdownRenderResult
# Database/Table: N/A (file artifact only; reports.file_path set by Report Service)
# Related Modules: docx_renderer, report_aggregation
# Important Notes: CMP-24 comparison blocks render stored contract_comparison
#   when present; legacy similarities/differences remain the fallback.
# =============================================================================

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.models.enums import ReportSourceType
from app.services.report_aggregation import AggregatedReportBlock
from app.services.renderers.common import (
    build_report_filename,
    build_report_object_key,
    cell_str,
    ensure_parent_dir,
    extraction_as_table,
    resolve_report_staging_path,
)


@dataclass(frozen=True, slots=True)
class MarkdownRenderResult:
    """Local staging artifact + MinIO object key for later upload."""

    filename: str
    local_path: Path
    object_key: str
    markdown: str
    section_count: int


def render_markdown(
    blocks: Sequence[AggregatedReportBlock],
    *,
    report_title: str,
    report_id: uuid.UUID,
    workspace_id: uuid.UUID,
    output_dir: Path | None = None,
) -> MarkdownRenderResult:
    """Render blocks to Markdown and write the staging ``.md`` file."""
    filename = build_report_filename(report_title, report_id, extension="md")
    object_key = build_report_object_key(
        workspace_id=workspace_id,
        report_id=report_id,
        filename=filename,
    )
    local_path = resolve_report_staging_path(
        workspace_id=workspace_id,
        report_id=report_id,
        filename=filename,
        output_dir=output_dir,
    )

    parts: list[str] = [f"# {report_title.strip() or 'Report'}", ""]
    for block in blocks:
        parts.append(f"## {block.title}")
        parts.append("")
        body = _render_block_body(block)
        if body:
            parts.append(body)
            parts.append("")

    markdown = "\n".join(parts).rstrip() + "\n"
    ensure_parent_dir(local_path)
    local_path.write_text(markdown, encoding="utf-8")

    return MarkdownRenderResult(
        filename=filename,
        local_path=local_path,
        object_key=object_key,
        markdown=markdown,
        section_count=len(blocks),
    )


def _render_block_body(block: AggregatedReportBlock) -> str:
    source_type = block.source_type
    if isinstance(source_type, str):
        try:
            source_type = ReportSourceType(source_type)
        except ValueError:
            return _json_fence(block.content)

    if source_type is ReportSourceType.summary:
        return _render_summary(block.content)
    if source_type is ReportSourceType.comparison:
        return _render_comparison(block.content)
    if source_type is ReportSourceType.extraction:
        return _render_extraction(block.content)
    if source_type is ReportSourceType.chat_session:
        return _render_chat(block.content)
    return _json_fence(block.content)


def _render_summary(content: dict[str, Any]) -> str:
    lines: list[str] = []
    text = content.get("text")
    if isinstance(text, str) and text.strip():
        lines.append(text.strip())

    sections = content.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = cell_str(section.get("title")).strip()
            body = cell_str(section.get("content")).strip()
            if title:
                lines.append(f"### {title}")
                lines.append("")
            if body:
                lines.append(body)
                lines.append("")

    return "\n".join(lines).rstrip()


def _render_comparison(content: dict[str, Any]) -> str:
    report = content.get("comparison_report")
    if isinstance(report, dict):
        return _render_contract_comparison(report, content)
    return _render_legacy_comparison(content)


def _render_legacy_comparison(content: dict[str, Any]) -> str:
    lines: list[str] = []
    similarities = content.get("similarities") or []
    differences = content.get("differences") or []

    if similarities:
        lines.append("### Similarities")
        lines.append("")
        for item in similarities:
            lines.append(f"- {cell_str(item)}")
        lines.append("")

    if differences:
        lines.append("### Differences")
        lines.append("")
        for item in differences:
            lines.append(f"- {cell_str(item)}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _render_contract_comparison(report: dict[str, Any], content: dict[str, Any]) -> str:
    lines: list[str] = []
    meta = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    summary = (
        report.get("executive_summary")
        if isinstance(report.get("executive_summary"), dict)
        else {}
    )
    stats = (
        report.get("overall_statistics")
        if isinstance(report.get("overall_statistics"), dict)
        else {}
    )
    risks = report.get("risk_summary") if isinstance(report.get("risk_summary"), dict) else {}
    generation = (
        report.get("generation_metadata")
        if isinstance(report.get("generation_metadata"), dict)
        else {}
    )

    lines.extend(["### Executive Summary", ""])
    if meta.get("comparison_id"):
        lines.append(f"Comparison ID: `{meta['comparison_id']}`")
    if meta.get("generated_at"):
        lines.append(f"Generated at: {meta['generated_at']}")
    if meta.get("status"):
        lines.append(f"Status: {meta['status']}")
    lines.append("")
    lines.append(f"- Total clauses: {summary.get('total_clauses', 0)}")
    lines.append(f"- UNCHANGED: {summary.get('unchanged', 0)}")
    lines.append(f"- MODIFIED: {summary.get('modified', 0)}")
    lines.append(f"- ADDED: {summary.get('added', 0)}")
    lines.append(f"- REMOVED: {summary.get('removed', 0)}")
    if summary.get("unresolved"):
        lines.append(f"- UNRESOLVED: {summary.get('unresolved')}")
    risk_counts = summary.get("risk_counts") if isinstance(summary.get("risk_counts"), dict) else {}
    lines.append(f"- CRITICAL risks: {risk_counts.get('CRITICAL', 0)}")
    lines.append(f"- HIGH risks: {risk_counts.get('HIGH', 0)}")
    lines.append(f"- Verified evidence references: {summary.get('verified_evidence_count', 0)}")
    lines.append("")

    lines.extend(["### Documents", ""])
    for doc in report.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        side = cell_str(doc.get("side")) or "Document"
        title = cell_str(doc.get("title")).strip()
        version = cell_str(doc.get("document_version_id")).strip()
        label = f"**{side}**"
        if title:
            label += f": {title}"
        if version:
            label += f" (version `{version}`)"
        lines.append(f"- {label}")
    lines.append("")

    lines.extend(["### Overall Statistics", ""])
    lines.append(f"- Clauses compared: {stats.get('total_clauses_compared', 0)}")
    if stats.get("verification_rate") is not None:
        lines.append(f"- Verification rate: {stats.get('verification_rate')}")
    if stats.get("llm_calls") is not None:
        lines.append(f"- Upstream LLM calls: {stats.get('llm_calls')}")
    lines.append("")

    lines.extend(["### Risk Summary", ""])
    level_rows = [
        [cell_str(item.get("level")), cell_str(item.get("count"))]
        for item in risks.get("by_level") or []
        if isinstance(item, dict)
    ]
    if level_rows:
        lines.append(_markdown_table(["Risk level", "Count"], level_rows))
        lines.append("")
    category_rows = [
        [cell_str(item.get("category")), cell_str(item.get("count"))]
        for item in risks.get("by_category") or []
        if isinstance(item, dict)
    ]
    if category_rows:
        lines.append(_markdown_table(["Risk category", "Count"], category_rows))
        lines.append("")
    for item in risks.get("items") or []:
        if not isinstance(item, dict):
            continue
        clause = cell_str(item.get("clause_id")) or "Clause"
        level = cell_str(item.get("risk_level")) or "—"
        category = cell_str(item.get("risk_category")) or "—"
        lines.append(f"- **{clause}** — {level} / {category}")
        if item.get("reason"):
            lines.append(f"  - Detected risk: {item['reason']}")
        if item.get("explanation"):
            lines.append(f"  - Risk explanation: {item['explanation']}")
        if item.get("recommendation"):
            lines.append(f"  - Recommendation: {item['recommendation']}")
    lines.append("")

    lines.extend(_clause_table_section("Changed Clauses", report.get("changed_clauses")))
    lines.extend(_clause_table_section("Added Clauses", report.get("added_clauses")))
    lines.extend(_clause_table_section("Removed Clauses", report.get("removed_clauses")))

    unchanged = (
        report.get("unchanged_clauses")
        if isinstance(report.get("unchanged_clauses"), dict)
        else {}
    )
    lines.extend(["### Unchanged Clauses", ""])
    count = unchanged.get("count", 0)
    lines.append(f"{count} clauses remained unchanged.")
    lines.append("")

    details = report.get("detailed_clause_comparisons") or []
    if details:
        lines.extend(["### Detailed Evidence", ""])
        for detail in details:
            if isinstance(detail, dict):
                lines.extend(_render_clause_detail(detail))

    lines.extend(["### Generation Metadata", ""])
    lines.append(f"- Builder: {generation.get('builder') or 'cmp-24'}")
    lines.append(f"- Source: {generation.get('source') or 'contract_comparison'}")
    lines.append(f"- Report LLM calls: {generation.get('llm_calls_report', 0)}")
    lines.append(f"- Upstream LLM calls: {generation.get('llm_calls_upstream', 0)}")
    if generation.get("quality_status"):
        lines.append(f"- Quality status: {generation['quality_status']}")
    lines.append("")

    legacy = _render_legacy_comparison(content)
    if legacy:
        lines.extend(["### Contextual notes", "", legacy, ""])

    return "\n".join(lines).rstrip()


def _clause_table_section(title: str, rows: object) -> list[str]:
    items = rows if isinstance(rows, list) else []
    lines = [f"### {title}", ""]
    if not items:
        lines.append("None.")
        lines.append("")
        return lines
    table_rows = [
        [
            cell_str(item.get("display_id") or item.get("clause_id")),
            cell_str(item.get("status")),
            cell_str(item.get("risk_level")) or "—",
            cell_str(item.get("risk_category")) or "—",
            cell_str(item.get("change")) or "—",
        ]
        for item in items
        if isinstance(item, dict)
    ]
    lines.append(
        _markdown_table(
            ["Clause", "Status", "Risk", "Category", "Change"],
            table_rows,
        )
    )
    lines.append("")
    return lines


def _render_clause_detail(detail: dict[str, Any]) -> list[str]:
    display = cell_str(detail.get("display_id") or detail.get("clause_id")) or "Clause"
    lines = [f"#### Clause {display}", ""]
    lines.append(f"- Status: {detail.get('status') or '—'}")
    if detail.get("risk_level"):
        lines.append(f"- Risk: {detail['risk_level']}")
    if detail.get("risk_category"):
        lines.append(f"- Category: {detail['risk_category']}")
    if detail.get("verification_status"):
        lines.append(f"- Citation verification: {detail['verification_status']}")
    lines.append("")
    if detail.get("v1_text") is not None:
        lines.extend(["**V1**", "", _fenced_text(detail["v1_text"]), ""])
    if detail.get("v2_text") is not None:
        lines.extend(["**V2**", "", _fenced_text(detail["v2_text"]), ""])
    diffs = detail.get("exact_differences") or []
    if diffs:
        lines.extend(["**Exact Changes**", ""])
        for item in diffs:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {cell_str(item.get('label')) or 'Value'}")
            if item.get("old") is not None:
                lines.append(f"  - V1: {item['old']}")
            if item.get("new") is not None:
                lines.append(f"  - V2: {item['new']}")
            if item.get("delta"):
                lines.append(f"  - Absolute delta: {item['delta']}")
            if item.get("percent"):
                lines.append(f"  - Percentage change: {item['percent']}")
        lines.append("")
    if detail.get("explanation"):
        lines.extend(["**Risk Explanation**", "", cell_str(detail["explanation"]), ""])
    if detail.get("recommendation"):
        lines.extend(["**Recommendation**", "", cell_str(detail["recommendation"]), ""])
    if detail.get("absence_note"):
        lines.extend(["**Absence / counterpart**", "", cell_str(detail["absence_note"]), ""])
    evidence = detail.get("evidence") or []
    if evidence:
        lines.extend(["**Evidence**", ""])
        for item in evidence:
            if not isinstance(item, dict):
                continue
            side = cell_str(item.get("side")) or "Source"
            state = _evidence_state_label(item.get("verification_state"))
            page = item.get("page_number")
            page_bit = f", page {page}" if page not in (None, "") else ""
            clause = cell_str(item.get("clause_id"))
            lines.append(f"- {side}{page_bit} — {state}")
            if clause:
                lines.append(f"  - Clause: {clause}")
            if item.get("display_text"):
                lines.append(f"  - Source: {item['display_text']}")
        lines.append("")
    return lines


def _evidence_state_label(state: object) -> str:
    key = cell_str(state).strip().lower()
    if key == "verified":
        return "Verified"
    if key == "partial":
        return "Partially verified"
    if key == "unavailable":
        return "No evidence"
    return "Unverified"


def _fenced_text(value: object) -> str:
    text = value if isinstance(value, str) else cell_str(value)
    return "```text\n" + text.replace("```", "'''") + "\n```"


def _render_extraction(content: dict[str, Any]) -> str:
    table = extraction_as_table(content)
    if table is not None:
        headers, rows = table
        return _markdown_table(headers, rows)

    result = content.get("result")
    payload = result if result is not None else content
    return _json_fence(payload)


def _render_chat(content: dict[str, Any]) -> str:
    messages = content.get("messages") or []
    lines: list[str] = []
    if not isinstance(messages, list):
        return _json_fence(content)

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = cell_str(message.get("role")).strip().lower()
        text = cell_str(message.get("content")).strip()
        if role == "user":
            label = "User"
        elif role == "assistant":
            label = "Assistant"
        else:
            label = role.title() or "Message"
        lines.append(f"**{label}:** {text}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers:
        return ""

    def esc(cell: str) -> str:
        return cell.replace("|", "\\|").replace("\n", " ")

    header_line = "| " + " | ".join(esc(h) for h in headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = [
        "| " + " | ".join(esc(c) for c in row) + " |" for row in rows
    ]
    return "\n".join([header_line, sep_line, *body_lines])


def _json_fence(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
