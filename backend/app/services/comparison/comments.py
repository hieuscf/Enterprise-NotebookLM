# =============================================================================
# File: comments.py
# Module/Service: Comparison Service (TASK-CMP-22)
# Layer: Service
# Purpose: Pure helpers for reviewer comments attached to comparison context.
# Responsibilities:
#   - Normalize, add, update, and delete comments without touching analysis
#   - Bind comments to clause / exact difference / evidence targets
# Dependencies:
#   - app.services.comparison.review (canonical clause ids)
# Public Exports:
#   - TARGET_TYPES, add_comment, update_comment, delete_comment,
#     find_comment, normalize_comments
# Database/Table: comparisons.comments
# Related Modules: ComparisonService.add_comment, app.schemas.comparisons
# Important Notes: Comments are reviewer context, never system analysis.
#   Do not mutate similarities, differences, contract_comparison, or review.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.services.comparison.review import canonical_clause_id, find_clause_row

TARGET_TYPES = frozenset({"CLAUSE", "FINDING", "EXACT_DIFFERENCE", "EVIDENCE"})
PERSISTED_TARGETS = frozenset({"CLAUSE", "EXACT_DIFFERENCE", "EVIDENCE"})
MAX_BODY_LENGTH = 4000
MAX_COMMENTS = 200


class CommentError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def normalize_target_type(raw: str | None) -> str:
    key = (raw or "CLAUSE").strip().upper()
    if key == "FINDING":
        return "CLAUSE"
    if key not in PERSISTED_TARGETS:
        raise CommentError("invalid_comment_target", "Unsupported comment target")
    return key


def normalize_comments(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        comment_id = str(item.get("id") or "").strip()
        clause_id = str(item.get("clause_id") or "").strip()
        body = str(item.get("body") or "").strip()
        if not comment_id or not clause_id or not body:
            continue
        if item.get("deleted_at"):
            continue
        try:
            target_type = normalize_target_type(str(item.get("target_type") or "CLAUSE"))
        except CommentError:
            continue
        target_id = str(item.get("target_id") or "").strip() or None
        if target_type == "CLAUSE":
            target_id = None
        author_name = str(item.get("author_name") or "").strip() or None
        author_id = str(item.get("author_id") or "").strip() or None
        out.append(
            {
                "id": comment_id,
                "clause_id": clause_id,
                "target_type": target_type,
                "target_id": target_id,
                "body": body,
                "author_id": author_id,
                "author_name": author_name,
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        )
    return out


def _evidence_ids(clause: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("evidence", "citations"):
        rows = clause.get(key)
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("evidence_id") or "").strip()
            if evidence_id:
                ids.add(evidence_id)
    return ids


def resolve_comment_target(
    result: dict[str, Any] | None,
    *,
    clause_id: str,
    target_type: str,
    target_id: str | None,
) -> tuple[str, str, str | None]:
    canonical = canonical_clause_id(result, clause_id)
    if canonical is None:
        raise CommentError("clause_not_found", "Clause not found in this comparison")
    normalized = normalize_target_type(target_type)
    if normalized == "CLAUSE":
        return canonical, "CLAUSE", None

    clause = find_clause_row(result, canonical)
    if clause is None:
        raise CommentError("clause_not_found", "Clause not found in this comparison")

    wanted = (target_id or "").strip()
    if not wanted:
        raise CommentError("invalid_comment_target", "Comment target is required")

    if normalized == "EXACT_DIFFERENCE":
        diffs = clause.get("exact_differences")
        rows = diffs if isinstance(diffs, list) else []
        try:
            index = int(wanted)
        except ValueError as exc:
            raise CommentError(
                "invalid_comment_target",
                "Exact difference target is invalid",
            ) from exc
        if index < 0 or index >= len(rows):
            raise CommentError("invalid_comment_target", "Exact difference not found")
        return canonical, "EXACT_DIFFERENCE", str(index)

    if wanted not in _evidence_ids(clause):
        raise CommentError("invalid_comment_target", "Evidence not found on this clause")
    return canonical, "EVIDENCE", wanted


def add_comment(
    existing: object,
    *,
    clause_id: str,
    target_type: str,
    target_id: str | None,
    body: str,
    author_id: UUID,
    author_name: str,
    created_at: datetime,
) -> list[dict[str, Any]]:
    text = (body or "").strip()
    if not text:
        raise CommentError("invalid_comment_body", "Comment body is required")
    if len(text) > MAX_BODY_LENGTH:
        raise CommentError("invalid_comment_body", "Comment body is too long")
    rows = list(existing) if isinstance(existing, list) else []
    active = [item for item in rows if isinstance(item, dict) and not item.get("deleted_at")]
    if len(active) >= MAX_COMMENTS:
        raise CommentError("comment_limit", "Too many comments on this comparison", 409)
    rows.append(
        {
            "id": str(uuid4()),
            "clause_id": clause_id,
            "target_type": target_type,
            "target_id": target_id,
            "body": text,
            "author_id": str(author_id),
            "author_name": (author_name or "").strip() or "Reviewer",
            "created_at": created_at.isoformat(),
            "updated_at": None,
        }
    )
    return rows


def find_comment(
    existing: object,
    comment_id: str,
    *,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    wanted = str(comment_id)
    rows = existing if isinstance(existing, list) else []
    for item in rows:
        if not isinstance(item, dict) or str(item.get("id") or "") != wanted:
            continue
        if item.get("deleted_at") and not include_deleted:
            return None
        return item
    return None


def update_comment(
    existing: object,
    *,
    comment_id: str,
    body: str,
    author_id: UUID,
    updated_at: datetime,
) -> list[dict[str, Any]]:
    text = (body or "").strip()
    if not text:
        raise CommentError("invalid_comment_body", "Comment body is required")
    if len(text) > MAX_BODY_LENGTH:
        raise CommentError("invalid_comment_body", "Comment body is too long")
    rows = list(existing) if isinstance(existing, list) else []
    wanted = str(comment_id)
    for index, item in enumerate(rows):
        if not isinstance(item, dict) or str(item.get("id") or "") != wanted:
            continue
        if item.get("deleted_at"):
            raise CommentError("comment_not_found", "Comment not found", 404)
        if str(item.get("author_id") or "") != str(author_id):
            raise CommentError(
                "comment_forbidden",
                "Only the author can edit this comment",
                403,
            )
        next_item = dict(item)
        next_item["body"] = text
        next_item["updated_at"] = updated_at.isoformat()
        rows[index] = next_item
        return rows
    raise CommentError("comment_not_found", "Comment not found", 404)


def delete_comment(existing: object, *, comment_id: str, deleted_at: datetime) -> list[dict[str, Any]]:
    rows = list(existing) if isinstance(existing, list) else []
    wanted = str(comment_id)
    for index, item in enumerate(rows):
        if not isinstance(item, dict) or str(item.get("id") or "") != wanted:
            continue
        if item.get("deleted_at"):
            raise CommentError("comment_not_found", "Comment not found", 404)
        next_item = dict(item)
        next_item["deleted_at"] = deleted_at.isoformat()
        rows[index] = next_item
        return rows
    raise CommentError("comment_not_found", "Comment not found", 404)
