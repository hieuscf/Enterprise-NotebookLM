/**
 * =============================================================================
 * File: comparison-comments.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-22 reviewer comments.
 * Responsibilities:
 *   - Normalize comments; filter by clause / exact difference / evidence
 *   - Present author lines without inferring analysis fields
 * Dependencies:
 *   - types/comparisons
 * Public Exports:
 *   - normalizeComments, commentsForTarget, commentCount, formatCommentMeta, …
 * Database/Table: N/A
 * Related Modules: ComparisonComments, ComparisonSummaryView
 * Important Notes: Comments are reviewer context. Never mix into system analysis.
 * =============================================================================
 */

import type {
  ComparisonComment,
  ComparisonCommentTarget,
} from "@/types/comparisons";

export type CommentTargetType = "CLAUSE" | "EXACT_DIFFERENCE" | "EVIDENCE";

export type CommentActions = {
  commenting?: boolean;
  onCommentCreate?: (
    clauseId: string,
    body: string,
    targetType: CommentTargetType,
    targetId?: string | null,
  ) => void;
  onCommentUpdate?: (commentId: string, body: string) => void;
  onCommentDelete?: (commentId: string) => void;
};

function asTargetType(raw: string | null | undefined): CommentTargetType {
  const key = String(raw ?? "CLAUSE").toUpperCase();
  if (key === "FINDING" || key === "CLAUSE") return "CLAUSE";
  if (key === "EXACT_DIFFERENCE") return "EXACT_DIFFERENCE";
  if (key === "EVIDENCE") return "EVIDENCE";
  return "CLAUSE";
}

export function normalizeComments(raw: ComparisonComment[] | null | undefined): ComparisonComment[] {
  if (!Array.isArray(raw)) return [];
  const out: ComparisonComment[] = [];
  for (const item of raw) {
    const id = String(item?.id ?? "").trim();
    const clauseId = String(item?.clause_id ?? "").trim();
    const body = String(item?.body ?? "").trim();
    if (!id || !clauseId || !body) continue;
    const targetType = asTargetType(item.target_type);
    const targetId = String(item.target_id ?? "").trim() || null;
    out.push({
      id,
      clause_id: clauseId,
      target_type: targetType,
      target_id: targetType === "CLAUSE" ? null : targetId,
      body,
      author_id: item.author_id ?? null,
      author_name: item.author_name ?? null,
      created_at: item.created_at ?? null,
      updated_at: item.updated_at ?? null,
    });
  }
  return out;
}

export function commentsForClause(
  comments: ComparisonComment[] | null | undefined,
  clauseId: string,
): ComparisonComment[] {
  const wanted = String(clauseId);
  return normalizeComments(comments).filter((item) => item.clause_id === wanted);
}

export function commentsForTarget(
  comments: ComparisonComment[] | null | undefined,
  clauseId: string,
  targetType: CommentTargetType = "CLAUSE",
  targetId?: string | null,
): ComparisonComment[] {
  const wantedId = String(targetId ?? "").trim() || null;
  return commentsForClause(comments, clauseId).filter((item) => {
    const type = asTargetType(item.target_type);
    if (type !== targetType) return false;
    if (targetType === "CLAUSE") return true;
    return String(item.target_id ?? "") === String(wantedId ?? "");
  });
}

export function commentCount(
  comments: ComparisonComment[] | null | undefined,
  clauseId?: string,
): number {
  if (!clauseId) return normalizeComments(comments).length;
  return commentsForClause(comments, clauseId).length;
}

export function commentBodiesForSearch(
  comments: ComparisonComment[] | null | undefined,
  clauseId: string,
): string {
  return commentsForClause(comments, clauseId)
    .map((item) => item.body)
    .join(" ");
}

export function exactDifferenceTargetId(index: number): string {
  return String(index);
}

export function targetTypeLabel(targetType: ComparisonCommentTarget): string {
  const key = asTargetType(String(targetType));
  if (key === "EXACT_DIFFERENCE") return "Khác biệt chính xác";
  if (key === "EVIDENCE") return "Bằng chứng";
  return "Điều khoản";
}

export function formatCommentTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export function formatCommentMeta(comment: ComparisonComment): string | null {
  const name = (comment.author_name ?? "").trim();
  const at = formatCommentTime(comment.updated_at ?? comment.created_at);
  const edited = Boolean(comment.updated_at);
  if (name && at) return `${name} · ${at}${edited ? " · đã sửa" : ""}`;
  if (name) return edited ? `${name} · đã sửa` : name;
  if (at) return edited ? `${at} · đã sửa` : at;
  return null;
}

export function commentCountLabel(count: number): string {
  if (count <= 0) return "Ghi chú";
  return `${count} ghi chú`;
}
