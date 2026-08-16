# =============================================================================
# File: comparison_report_builder.py
# Module/Service: Report Service (FR9 / TASK-CMP-24)
# Layer: Service
# Purpose: Turn a stored comparison result into a structured, auditable report
#   model for Markdown/DOCX/PDF rendering. Zero LLM calls.
# Responsibilities:
#   - Unwrap contract_comparison; project metadata, stats, risks, clauses
#   - Preserve original clause text, exact diffs, evidence, verification
#   - Never remap, rescore, retrieve, or infer absence from missing chunks
# Dependencies:
#   - app.services.comparison.review (unwrap_contract_report, clause_rows)
# Public Exports:
#   - build_comparison_report_content, CONSERVATIVE_ABSENCE_MESSAGE
# Database/Table: comparisons.result (read-only)
# Related Modules: report_aggregation, markdown_renderer, docx_renderer
# Important Notes:
#   - Presentation only. Classification/risk/evidence come from upstream.
#   - Page presence is never treated as verified evidence.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.services.comparison.review import clause_rows, unwrap_contract_report

CONSERVATIVE_ABSENCE_MESSAGE = (
    "Chưa đủ bằng chứng để xác định điều khoản tương ứng không tồn tại "
    "trong phiên bản còn lại."
)
ABSENCE_CONFIRMED_MESSAGE = (
    "Xác minh đã xác nhận không có điều khoản tương ứng trong phiên bản còn lại."
)

_RISK_LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
_VERIFIED = frozenset({"VERIFIED", "VALID"})
_CLAUSE_PREFIX = ("CLAUSE:", "ARTICLE:", "APPENDIX:", "SECTION:")


def build_comparison_report_content(
    *,
    result: dict[str, Any] | None,
    comparison_id: UUID | str | None = None,
    workspace_id: UUID | str | None = None,
    title: str | None = None,
    status: str | None = None,
    created_at: datetime | str | None = None,
    document_titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build renderer content. Always keeps similarities/differences for FR8."""
    payload = result if isinstance(result, dict) else {}
    similarities = _string_list(payload.get("similarities"))
    differences = _string_list(payload.get("differences"))
    report = unwrap_contract_report(payload)
    content: dict[str, Any] = {
        "similarities": similarities,
        "differences": differences,
        "has_contract_report": report is not None,
        "comparison_report": None,
    }
    if report is None:
        return content
    content["comparison_report"] = _project_report(
        report,
        comparison_id=comparison_id,
        workspace_id=workspace_id,
        title=title,
        status=status,
        created_at=created_at,
        document_titles=document_titles or {},
    )
    return content


def _project_report(
    report: dict[str, Any],
    *,
    comparison_id: UUID | str | None,
    workspace_id: UUID | str | None,
    title: str | None,
    status: str | None,
    created_at: datetime | str | None,
    document_titles: dict[str, str],
) -> dict[str, Any]:
    metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    statistics = (
        report.get("statistics") if isinstance(report.get("statistics"), dict) else {}
    )
    rows = clause_rows(report)
    modified = [row for row in rows if _status(row) == "MODIFIED"]
    added = [row for row in rows if _status(row) == "ADDED"]
    removed = [row for row in rows if _status(row) == "REMOVED"]
    unchanged = [row for row in rows if _status(row) == "UNCHANGED"]
    unresolved = [row for row in rows if _status(row) == "UNRESOLVED"]

    exec_summary = _executive_summary(summary, statistics, rows, unchanged, unresolved)
    documents = _documents(metadata, document_titles)
    return {
        "metadata": {
            "title": (title or "").strip() or "Contract Comparison Report",
            "comparison_id": _as_text(comparison_id) or _as_text(metadata.get("comparison_id")),
            "workspace_id": _as_text(workspace_id) or _as_text(metadata.get("workspace_id")),
            "generated_at": _as_iso(created_at) or _as_text(metadata.get("created_at")),
            "status": (status or _as_text(metadata.get("status")) or "").strip() or None,
            "quality_status": _as_text(metadata.get("quality_status")),
        },
        "executive_summary": exec_summary,
        "documents": documents,
        "overall_statistics": _overall_statistics(statistics, exec_summary),
        "risk_summary": _risk_summary(report, rows),
        "changed_clauses": [_clause_summary_row(row) for row in modified],
        "added_clauses": [_clause_summary_row(row) for row in added],
        "removed_clauses": [_clause_summary_row(row) for row in removed],
        "unchanged_clauses": {
            "count": exec_summary["unchanged"],
            "clause_ids": [_as_text(row.get("clause_id")) for row in unchanged if row.get("clause_id")],
        },
        "detailed_clause_comparisons": [
            _detailed_clause(row) for row in (*modified, *added, *removed)
        ],
        "generation_metadata": {
            "builder": "cmp-24",
            "source": "contract_comparison",
            "llm_calls_upstream": _as_int(statistics.get("llm_calls")),
            "llm_calls_report": 0,
            "quality_status": _as_text(metadata.get("quality_status")),
            "quality_reasons": list(metadata.get("quality_reasons") or [])
            if isinstance(metadata.get("quality_reasons"), list)
            else [],
            "explanation_incomplete": bool(metadata.get("explanation_incomplete")),
        },
    }


def _executive_summary(
    summary: dict[str, Any],
    statistics: dict[str, Any],
    rows: list[dict[str, Any]],
    unchanged: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = {
        "total_clauses": _as_int(summary.get("total_clauses")),
        "unchanged": _as_int(summary.get("unchanged")),
        "modified": _as_int(summary.get("modified")),
        "added": _as_int(summary.get("added")),
        "removed": _as_int(summary.get("removed")),
        "unresolved": _as_int(statistics.get("unresolved")),
    }
    if counts["total_clauses"] == 0 and rows:
        by_status = {
            "UNCHANGED": 0,
            "MODIFIED": 0,
            "ADDED": 0,
            "REMOVED": 0,
            "UNRESOLVED": 0,
        }
        for row in rows:
            key = _status(row)
            if key in by_status:
                by_status[key] += 1
        counts = {
            "total_clauses": len(rows),
            "unchanged": by_status["UNCHANGED"],
            "modified": by_status["MODIFIED"],
            "added": by_status["ADDED"],
            "removed": by_status["REMOVED"],
            "unresolved": by_status["UNRESOLVED"],
        }
    elif counts["unresolved"] == 0 and unresolved:
        counts["unresolved"] = len(unresolved)

    risk_counts = _risk_counts(statistics, rows)
    return {
        **counts,
        "risk_counts": risk_counts,
        "risk_total": sum(risk_counts.values()),
        "high_risks": risk_counts["HIGH"],
        "critical_risks": risk_counts["CRITICAL"],
        "verified_evidence_count": _verified_evidence_count(rows),
    }


def _overall_statistics(
    statistics: dict[str, Any],
    exec_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "total_clauses_compared": _as_int(statistics.get("total_clauses_compared"))
        or exec_summary["total_clauses"],
        "unchanged": _as_int(statistics.get("unchanged")) or exec_summary["unchanged"],
        "modified": _as_int(statistics.get("modified")) or exec_summary["modified"],
        "added": _as_int(statistics.get("added")) or exec_summary["added"],
        "removed": _as_int(statistics.get("removed")) or exec_summary["removed"],
        "unresolved": _as_int(statistics.get("unresolved")) or exec_summary["unresolved"],
        "risk_counts": exec_summary["risk_counts"],
        "verification_rate": statistics.get("verification_rate"),
        "citation_verification_rate": statistics.get("citation_verification_rate"),
        "llm_calls": _as_int(statistics.get("llm_calls")),
        "processing_time_ms": _as_int(statistics.get("processing_time_ms")),
    }


def _risk_counts(statistics: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, int]:
    raw = statistics.get("risk_counts")
    counts = {level: 0 for level in _RISK_LEVELS}
    if isinstance(raw, dict) and raw:
        for key, value in raw.items():
            level = str(key or "").upper()
            if level in counts:
                counts[level] = _as_int(value)
        if any(counts.values()):
            return counts
    for row in rows:
        level = _risk_level(row)
        if level in counts:
            counts[level] += 1
    return counts


def _risk_summary(report: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    stored_risks = report.get("risks")
    if isinstance(stored_risks, list):
        for item in stored_risks:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "clause_id": _as_text(item.get("clause_id") or item.get("identity_key")),
                    "status": _as_text(item.get("status")),
                    "risk_level": _upper(item.get("risk_level")),
                    "risk_category": _upper(item.get("risk_category")),
                    "reason": _as_text(item.get("reason")),
                    "explanation": _as_text(item.get("explanation")),
                    "recommendation": _as_text(item.get("recommendation")),
                }
            )
    if not items:
        for row in rows:
            risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
            if not risk and not _explanation_text(row) and not _recommendation(row):
                continue
            if not _risk_level(row) and not _risk_category(row) and not risk.get("reason"):
                continue
            items.append(
                {
                    "clause_id": _as_text(row.get("clause_id")),
                    "status": _status(row),
                    "risk_level": _risk_level(row),
                    "risk_category": _risk_category(row),
                    "reason": _as_text(risk.get("reason")),
                    "explanation": _explanation_text(row),
                    "recommendation": _recommendation(row),
                }
            )

    by_level: dict[str, int] = {level: 0 for level in _RISK_LEVELS}
    by_category: dict[str, int] = {}
    for item in items:
        level = item.get("risk_level")
        if level in by_level:
            by_level[level] += 1
        category = item.get("risk_category")
        if category:
            by_category[category] = by_category.get(category, 0) + 1
    return {
        "by_level": [{"level": level, "count": by_level[level]} for level in _RISK_LEVELS],
        "by_category": [
            {"category": key, "count": by_category[key]}
            for key in sorted(by_category)
        ],
        "items": items,
    }


def _documents(
    metadata: dict[str, Any],
    document_titles: dict[str, str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for side, key in (("V1", "document_v1"), ("V2", "document_v2")):
        raw = metadata.get(key)
        ref = raw if isinstance(raw, dict) else {}
        doc_id = _as_text(ref.get("document_id"))
        title = _as_text(ref.get("title")) or (document_titles.get(doc_id) if doc_id else None)
        out.append(
            {
                "side": side,
                "title": title,
                "document_id": doc_id,
                "document_version_id": _as_text(ref.get("document_version_id")),
            }
        )
    return out


def _clause_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "clause_id": _as_text(row.get("clause_id")),
        "display_id": display_clause_id(row.get("clause_id")),
        "status": _status(row),
        "risk_level": _risk_level(row),
        "risk_category": _risk_category(row),
        "change": _change_summary(row),
    }


def _detailed_clause(row: dict[str, Any]) -> dict[str, Any]:
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    return {
        "clause_id": _as_text(row.get("clause_id")),
        "display_id": display_clause_id(row.get("clause_id")),
        "status": _status(row),
        "risk_level": _risk_level(row),
        "risk_category": _risk_category(row),
        "v1_text": _original_text(row.get("v1_text")),
        "v2_text": _original_text(row.get("v2_text")),
        "exact_differences": [_exact_difference(item) for item in _dict_list(row.get("exact_differences"))],
        "explanation": _explanation_text(row),
        "recommendation": _recommendation(row),
        "verification_status": _upper(verification.get("status")),
        "verification_message": _as_text(verification.get("human_message")),
        "absence_status": _upper(verification.get("absence_status")),
        "absence_note": _absence_note(row),
        "evidence": _project_evidence(row),
    }


def _exact_difference(item: dict[str, Any]) -> dict[str, Any]:
    old = item.get("old") if isinstance(item.get("old"), dict) else {}
    new = item.get("new") if isinstance(item.get("new"), dict) else {}
    old_display = _as_text(old.get("raw")) or _as_text(old.get("value"))
    new_display = _as_text(new.get("raw")) or _as_text(new.get("value"))
    delta = _as_text(item.get("delta"))
    unit = _as_text(item.get("delta_unit"))
    percent = _as_text(item.get("relative_change_percent"))
    return {
        "label": _as_text(item.get("value_type")) or _as_text(item.get("change_type")) or "Value",
        "old": old_display,
        "new": new_display,
        "delta": f"{delta} {unit}" if delta and unit else delta,
        "percent": f"{percent}%" if percent else None,
        "context": _as_text(item.get("context")),
    }


def _project_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    results = _dict_list(verification.get("evidence_results"))
    by_id = {
        _as_text(item.get("evidence_id")): _upper(item.get("status"))
        for item in results
        if item.get("evidence_id")
    }
    verified_ids = {
        _as_text(item)
        for item in (verification.get("verified_evidence_ids") or [])
        if item
    }
    sources = row.get("citations") if isinstance(row.get("citations"), list) and row.get("citations") else row.get("evidence")
    out: list[dict[str, Any]] = []
    for item in _dict_list(sources):
        evidence_id = _as_text(item.get("evidence_id"))
        item_status = by_id.get(evidence_id)
        state = _evidence_state(
            item_status=item_status,
            clause_status=_upper(verification.get("status")),
            evidence_id=evidence_id,
            verified_ids=verified_ids,
        )
        out.append(
            {
                "evidence_id": evidence_id,
                "side": _upper(item.get("side")) or None,
                "document_title": None,
                "document_id": _as_text(item.get("document_id")),
                "document_version_id": _as_text(item.get("document_version_id")),
                "clause_id": _as_text(item.get("clause_id")) or _as_text(row.get("clause_id")),
                "chunk_id": _as_text(item.get("chunk_id")),
                "page_number": item.get("page_number"),
                "display_text": _original_text(item.get("display_text")),
                "source_type": _as_text(item.get("source_type")),
                "role": _as_text(item.get("role")),
                "verification_state": state,
            }
        )
    return out


def _evidence_state(
    *,
    item_status: str | None,
    clause_status: str | None,
    evidence_id: str | None,
    verified_ids: set[str],
) -> str:
    if item_status in _VERIFIED or (evidence_id and evidence_id in verified_ids):
        return "verified"
    if item_status in {"INVALID", "MISMATCH", "MISSING"}:
        return "unverified"
    if clause_status == "VERIFIED":
        return "verified"
    if clause_status == "PARTIALLY_VERIFIED":
        return "partial"
    if clause_status in {"INSUFFICIENT_EVIDENCE", "UNVERIFIED", "INVALID"}:
        return "unverified"
    return "unverified"


def _verified_evidence_count(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        for item in _project_evidence(row):
            if item["verification_state"] == "verified":
                count += 1
    return count


def _absence_note(row: dict[str, Any]) -> str | None:
    status = _status(row)
    if status not in {"ADDED", "REMOVED"}:
        return None
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    message = _as_text(verification.get("human_message"))
    absence = _upper(verification.get("absence_status"))
    if absence == "ABSENCE_CONFIRMED":
        return message or ABSENCE_CONFIRMED_MESSAGE
    return message or CONSERVATIVE_ABSENCE_MESSAGE


def _change_summary(row: dict[str, Any]) -> str | None:
    diffs = _dict_list(row.get("exact_differences"))
    if diffs:
        first = _exact_difference(diffs[0])
        parts = [first["label"]]
        if first["old"] or first["new"]:
            parts.append(f"{first['old'] or '—'} → {first['new'] or '—'}")
        return " · ".join(part for part in parts if part)
    risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
    return _as_text(risk.get("reason"))


def _explanation_text(row: dict[str, Any]) -> str | None:
    explanation = row.get("explanation")
    if not isinstance(explanation, dict):
        return None
    output = explanation.get("output")
    if isinstance(output, dict):
        return _as_text(output.get("explanation"))
    return _as_text(explanation.get("explanation"))


def _recommendation(row: dict[str, Any]) -> str | None:
    explanation = row.get("explanation")
    if isinstance(explanation, dict):
        output = explanation.get("output")
        if isinstance(output, dict):
            text = _as_text(output.get("recommendation"))
            if text:
                return text
        text = _as_text(explanation.get("recommendation"))
        if text:
            return text
    risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
    return _as_text(risk.get("recommendation"))


def display_clause_id(value: object) -> str:
    text = _as_text(value) or "—"
    upper = text.upper()
    for prefix in _CLAUSE_PREFIX:
        if upper.startswith(prefix):
            return text[len(prefix) :]
    return text


def _status(row: dict[str, Any]) -> str:
    return _upper(row.get("status")) or "UNRESOLVED"


def _risk_level(row: dict[str, Any]) -> str | None:
    risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
    return _upper(risk.get("risk_level"))


def _risk_category(row: dict[str, Any]) -> str | None:
    risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
    return _upper(risk.get("risk_category"))


def _original_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value != "" else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _upper(value: object) -> str | None:
    text = _as_text(value)
    return text.upper() if text else None


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _as_iso(value: datetime | str | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return _as_text(value)
