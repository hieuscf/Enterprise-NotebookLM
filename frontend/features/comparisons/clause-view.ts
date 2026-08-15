/**
 * =============================================================================
 * File: clause-view.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-18 side-by-side clause comparison view.
 * Responsibilities:
 *   - Resolve selected clause / prev-next within the active filter list
 *   - Map V1/V2 identities; render backend source spans (not a frontend diff)
 *   - Absence / unchanged copy; exact-difference labels; comparison deep-links
 * Dependencies:
 *   - comparison-summary helpers, types/comparisons
 * Public Exports:
 *   - resolveClauseId, clauseNav, versionMapping, highlightSegments, …
 * Database/Table: N/A
 * Related Modules: ClauseComparisonView, ComparisonSummaryView
 * Important Notes: Do not classify ADDED/REMOVED/MODIFIED. Offsets come from API.
 *   Keep pure for node smoke tests (no React). Clause text is never put in URLs.
 * =============================================================================
 */

import { displayClauseId } from "@/features/comparisons/comparison-summary";
import type { ContractClauseResult, ContractExactDifference } from "@/types/comparisons";

export type ClauseNav = {
  index: number;
  total: number;
  prevId: string | null;
  nextId: string | null;
};

export type VersionMapping = {
  v1Id: string | null;
  v2Id: string | null;
  v1Label: string;
  v2Label: string;
  renumbered: boolean;
};

export type HighlightKind = "plain" | "removed" | "added";

export type HighlightSegment = {
  text: string;
  kind: HighlightKind;
};

const VALUE_TYPE_LABELS: Record<string, string> = {
  MONEY: "Số tiền",
  PERCENTAGE: "Tỷ lệ",
  DATE: "Ngày",
  DURATION: "Thời hạn",
  QUANTITY: "Số lượng",
  ENTITY: "Bên / thực thể",
  LOCATION: "Địa điểm",
};

export function resolveClauseId(
  clauses: ContractClauseResult[],
  param: string | null | undefined,
): string | null {
  const raw = (param ?? "").trim();
  if (!raw) return null;
  const upper = raw.toUpperCase();
  for (const clause of clauses) {
    const ids = [clause.clause_id, clause.v1_clause_id, clause.v2_clause_id]
      .filter(Boolean)
      .map((id) => String(id));
    if (ids.some((id) => id === raw || id.toUpperCase() === upper)) {
      return clause.clause_id;
    }
    if (displayClauseId(clause.clause_id) === raw) return clause.clause_id;
  }
  return null;
}

export function clauseNav(
  visible: ContractClauseResult[],
  currentId: string | null,
): ClauseNav {
  const total = visible.length;
  if (!currentId || total === 0) {
    return { index: -1, total, prevId: null, nextId: null };
  }
  const index = visible.findIndex((clause) => clause.clause_id === currentId);
  if (index < 0) {
    return { index: -1, total, prevId: null, nextId: null };
  }
  return {
    index,
    total,
    prevId: index > 0 ? visible[index - 1].clause_id : null,
    nextId: index < total - 1 ? visible[index + 1].clause_id : null,
  };
}

export function positionLabel(
  nav: ClauseNav,
  filterLabel: string,
): string {
  if (nav.index < 0 || nav.total === 0) return filterLabel;
  return `${filterLabel} · ${nav.index + 1} / ${nav.total}`;
}

export function versionMapping(clause: ContractClauseResult): VersionMapping {
  const v1Id = clause.v1_clause_id ?? (String(clause.status).toUpperCase() === "ADDED" ? null : clause.clause_id);
  const v2Id = clause.v2_clause_id ?? (String(clause.status).toUpperCase() === "REMOVED" ? null : clause.clause_id);
  const v1Label = v1Id ? displayClauseId(v1Id) : "—";
  const v2Label = v2Id ? displayClauseId(v2Id) : "—";
  return {
    v1Id,
    v2Id,
    v1Label,
    v2Label,
    renumbered: Boolean(v1Id && v2Id && v1Label !== v2Label),
  };
}

export function absenceMessage(status: string, side: "v1" | "v2"): string {
  const key = status.toUpperCase();
  if (key === "ADDED" && side === "v1") {
    return "Không xác định được điều khoản tương ứng ở V1";
  }
  if (key === "REMOVED" && side === "v2") {
    return "Không xác định được điều khoản tương ứng ở V2";
  }
  return side === "v1" ? "Không có nội dung V1" : "Không có nội dung V2";
}

export function unchangedCaption(): string {
  return "Không phát hiện khác biệt vật chất";
}

export function shouldEmphasizeDiff(status: string): boolean {
  return String(status).toUpperCase() === "MODIFIED";
}

export function shouldShowAiAnalysis(status: string): boolean {
  const key = String(status).toUpperCase();
  return key === "MODIFIED" || key === "ADDED" || key === "REMOVED";
}

export function parseOffset(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  const start = Number(value[0]);
  const end = Number(value[1]);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  if (start < 0 || end <= start) return null;
  return [Math.floor(start), Math.floor(end)];
}

function collectMarks(
  text: string,
  diffs: ContractExactDifference[],
  side: "v1" | "v2",
): Array<{ start: number; end: number; kind: Exclude<HighlightKind, "plain"> }> {
  if (!text) return [];
  const marks: Array<{ start: number; end: number; kind: Exclude<HighlightKind, "plain"> }> = [];
  for (const row of diffs) {
    const fromPair = parseOffset(side === "v1" ? row.source_offset : row.target_offset);
    const fromValue =
      side === "v1"
        ? parseOffset(
            row.old && typeof row.old.start === "number" && typeof row.old.end === "number"
              ? [row.old.start, row.old.end]
              : null,
          )
        : parseOffset(
            row.new && typeof row.new.start === "number" && typeof row.new.end === "number"
              ? [row.new.start, row.new.end]
              : null,
          );
    const span = fromPair ?? fromValue;
    if (!span) continue;
    const start = Math.max(0, span[0]);
    const end = Math.min(text.length, span[1]);
    if (end <= start) continue;
    marks.push({
      start,
      end,
      kind: side === "v1" ? "removed" : "added",
    });
  }
  marks.sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: typeof marks = [];
  for (const mark of marks) {
    const last = merged[merged.length - 1];
    if (last && mark.start <= last.end && mark.kind === last.kind) {
      last.end = Math.max(last.end, mark.end);
    } else {
      merged.push({ ...mark });
    }
  }
  return merged;
}

export function highlightSegments(
  text: string,
  diffs: ContractExactDifference[] | undefined,
  side: "v1" | "v2",
  status: string,
): HighlightSegment[] {
  if (!text) return [];
  if (!shouldEmphasizeDiff(status) || !diffs?.length) {
    return [{ text, kind: "plain" }];
  }
  const marks = collectMarks(text, diffs, side);
  if (marks.length === 0) return [{ text, kind: "plain" }];
  const segments: HighlightSegment[] = [];
  let cursor = 0;
  for (const mark of marks) {
    if (mark.start > cursor) {
      segments.push({ text: text.slice(cursor, mark.start), kind: "plain" });
    }
    segments.push({ text: text.slice(mark.start, mark.end), kind: mark.kind });
    cursor = mark.end;
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), kind: "plain" });
  }
  return segments;
}

export function valueTypeLabel(valueType: string | null | undefined): string {
  const key = String(valueType ?? "").toUpperCase();
  return VALUE_TYPE_LABELS[key] ?? (valueType ? String(valueType) : "Giá trị");
}

export function mappingConfidenceLabel(
  value: number | null | undefined,
): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const pct = value <= 1 ? Math.round(value * 100) : Math.round(value);
  if (pct < 0 || pct > 100) return null;
  return `${pct}%`;
}

export function userFacingRules(rules: string[] | null | undefined): string[] {
  if (!Array.isArray(rules)) return [];
  return rules
    .map((item) => String(item ?? "").trim())
    .filter((item) => item && !/^[0-9a-f-]{32,}$/i.test(item));
}

export function buildComparisonsHref(
  workspaceId: string,
  comparisonId: string | null | undefined,
  clauseId: string | null | undefined,
): string {
  const params = new URLSearchParams();
  if (comparisonId) params.set("comparison", comparisonId);
  if (clauseId) params.set("clause", clauseId);
  const qs = params.toString();
  const base = `/workspaces/${workspaceId}/comparisons`;
  return qs ? `${base}?${qs}` : base;
}

export function filterLabel(filter: string): string {
  switch (filter) {
    case "changed":
      return "Có thay đổi";
    case "modified":
      return "Đã sửa";
    case "added":
      return "Thêm mới";
    case "removed":
      return "Đã xoá";
    case "unchanged":
      return "Không đổi";
    default:
      return filter.trim() ? filter : "Tất cả";
  }
}

export function columnHeading(side: "v1" | "v2"): { kicker: string; title: string } {
  if (side === "v1") return { kicker: "Phiên bản 1", title: "Nguyên bản" };
  return { kicker: "Phiên bản 2", title: "Bản cập nhật" };
}
