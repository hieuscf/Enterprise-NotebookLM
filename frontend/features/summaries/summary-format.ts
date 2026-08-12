/**
 * =============================================================================
 * File: summary-format.ts
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for Summary labels, selection, and copy text (FR6).
 * Responsibilities:
 *   - Style labels (vi-VN); getCurrentSummary selection algorithm
 *   - Build clipboard text from content / by_topic sections
 * Dependencies:
 *   - types/summaries
 * Public Exports:
 *   - SUMMARY_STYLE_OPTIONS, styleLabel, statusLabel, getCurrentSummary,
 *     formatSummaryDateTime, buildCopyText, isOldVersion
 * Database/Table: N/A
 * Related Modules: features/summaries/*, scripts/test-summary-ui.mjs
 * Important Notes: Selection never picks an old-version summary as "current".
 * =============================================================================
 */

import type { Summary, SummaryStyle, SummaryStatus } from "@/types/summaries";

export const SUMMARY_STYLE_OPTIONS: ReadonlyArray<{
  style: SummaryStyle;
  label: string;
}> = [
  { style: "short", label: "Tóm tắt ngắn" },
  { style: "detailed", label: "Tóm tắt chi tiết" },
  { style: "by_topic", label: "Theo chủ đề" },
  { style: "bullet_points", label: "Gạch đầu dòng" },
];

export function styleLabel(style: SummaryStyle): string {
  return SUMMARY_STYLE_OPTIONS.find((o) => o.style === style)?.label ?? style;
}

export function statusLabel(status: SummaryStatus): string {
  switch (status) {
    case "processing":
      return "Đang tạo";
    case "completed":
      return "Hoàn tất";
    case "failed":
      return "Thất bại";
    default:
      return status;
  }
}

export function isOldVersion(
  summary: Pick<Summary, "source_version_id">,
  currentVersionId: string | null,
): boolean {
  if (!currentVersionId) return false;
  return summary.source_version_id !== currentVersionId;
}

/**
 * Selection priority:
 * 1. completed
 * 2. matching selected style
 * 3. matching current_version_id
 * 4. newest created_at
 *
 * Returns null when no current-version completed Summary exists for the style.
 */
export function getCurrentSummary(
  summaries: readonly Summary[],
  currentVersionId: string | null,
  selectedStyle: SummaryStyle,
): Summary | null {
  if (!currentVersionId) return null;
  const matches = summaries.filter(
    (s) =>
      s.status === "completed" &&
      s.style === selectedStyle &&
      s.source_version_id === currentVersionId,
  );
  if (matches.length === 0) return null;
  return [...matches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
}

/** Latest processing summary for style + current version (if any). */
export function getProcessingSummary(
  summaries: readonly Summary[],
  currentVersionId: string | null,
  selectedStyle: SummaryStyle,
): Summary | null {
  if (!currentVersionId) return null;
  const matches = summaries.filter(
    (s) =>
      s.status === "processing" &&
      s.style === selectedStyle &&
      s.source_version_id === currentVersionId,
  );
  if (matches.length === 0) return null;
  return [...matches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
}

/** Latest failed summary for style + current version (if any). */
export function getFailedSummary(
  summaries: readonly Summary[],
  currentVersionId: string | null,
  selectedStyle: SummaryStyle,
): Summary | null {
  if (!currentVersionId) return null;
  const matches = summaries.filter(
    (s) =>
      s.status === "failed" &&
      s.style === selectedStyle &&
      s.source_version_id === currentVersionId,
  );
  if (matches.length === 0) return null;
  return [...matches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
}

export function formatSummaryDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function buildCopyText(summary: Summary): string {
  if (summary.style === "by_topic" && summary.sections && summary.sections.length > 0) {
    return summary.sections
      .map((s) => `${s.title}\n${s.content}`.trim())
      .join("\n\n");
  }
  return (summary.content ?? "").trim();
}
