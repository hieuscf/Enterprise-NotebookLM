/**
 * =============================================================================
 * File: comparison-evidence.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-19 evidence & citation panel.
 * Responsibilities:
 *   - Group backend evidence by V1/V2; map verification from API fields only
 *   - Build source locations, excerpts, copy text, AI evidence-id links
 * Dependencies:
 *   - comparison-summary, clause-view, types/comparisons
 * Public Exports:
 *   - groupedEvidence, itemVerificationState, sourceTypeLabel, copyCitationText, …
 * Database/Table: N/A
 * Related Modules: ComparisonEvidencePanel, ClauseComparisonView
 * Important Notes: Never infer verified from page/text match. Keep pure for tests.
 * =============================================================================
 */

import { absenceMessage } from "@/features/comparisons/clause-view";
import {
  displayClauseId,
  evidenceState,
  evidenceViewerHref,
  formatExactDifference,
  shortChangeSummary,
  type EvidenceUiState,
} from "@/features/comparisons/comparison-summary";
import type {
  ContractClauseResult,
  ContractComparisonReport,
  ContractEvidenceRef,
} from "@/types/comparisons";

export type EvidenceVersionGroup = "v1" | "v2" | "other";

export type EvidenceListItem = {
  key: string;
  evidence: ContractEvidenceRef;
  side: EvidenceVersionGroup;
  verification: EvidenceUiState;
  primary: boolean;
  excerpt: string | null;
  locationLabel: string;
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  TEXT_SPAN: "Đoạn nguồn",
  CHUNK: "Đoạn văn",
  CLAUSE: "Điều khoản",
  PAGE: "Trang",
};

export function sourceTypeLabel(value: string | null | undefined): string | null {
  const key = String(value ?? "").trim().toUpperCase();
  if (!key) return null;
  return SOURCE_TYPE_LABELS[key] ?? null;
}

export function evidenceSide(item: ContractEvidenceRef): EvidenceVersionGroup {
  const side = String(item.side ?? "").toUpperCase();
  if (side === "OLD") return "v1";
  if (side === "NEW") return "v2";
  return "other";
}

export function isPrimaryEvidence(item: ContractEvidenceRef): boolean {
  return String(item.role ?? "").toUpperCase() === "PRIMARY";
}

function itemCheckStatus(
  clause: ContractClauseResult,
  evidenceId: string | null,
): string | null {
  if (!evidenceId) return null;
  const rows = clause.verification?.evidence_results ?? [];
  const match = rows.find((row) => row.evidence_id === evidenceId);
  return match?.status ? String(match.status).toUpperCase() : null;
}

export function itemVerificationState(
  clause: ContractClauseResult,
  item: ContractEvidenceRef,
): EvidenceUiState {
  const id = item.evidence_id ? String(item.evidence_id) : null;
  const check = itemCheckStatus(clause, id);
  if (check === "VALID") return "verified";
  if (check === "INVALID" || check === "MISMATCH") return "unverified";
  if (check === "MISSING" || check === "UNAVAILABLE") return "unavailable";

  const verifiedIds = clause.verification?.verified_evidence_ids ?? [];
  const invalidIds = clause.verification?.invalid_evidence_ids ?? [];
  if (id && verifiedIds.includes(id)) return "verified";
  if (id && invalidIds.includes(id)) return "unverified";

  const finding = String(clause.verification?.status ?? "").toUpperCase();
  if (finding === "INSUFFICIENT_EVIDENCE") return "unavailable";
  if (finding === "PARTIALLY_VERIFIED") return "partial";
  if (finding === "VERIFIED") return "unverified";
  if (finding === "INVALID") return "unverified";
  return evidenceState(clause);
}

export function evidenceExcerpt(
  item: ContractEvidenceRef,
  clause: ContractClauseResult,
): string | null {
  const provided = (item.display_text ?? "").trim();
  if (provided) return provided;
  const start = item.start_offset;
  const end = item.end_offset;
  if (typeof start !== "number" || typeof end !== "number" || end <= start) {
    return null;
  }
  const side = evidenceSide(item);
  const source = side === "v2" ? clause.v2_text : clause.v1_text;
  if (!source || end > source.length || start < 0) return null;
  return source.slice(start, end);
}

export function sourceLocationLabel(
  item: ContractEvidenceRef,
  documentTitle?: string | null,
): string {
  const parts: string[] = [];
  const title = (documentTitle ?? "").trim();
  if (title) parts.push(title);
  if (item.clause_id) parts.push(`Điều ${displayClauseId(item.clause_id)}`);
  if (typeof item.page_number === "number" && item.page_number > 0) {
    parts.push(`Trang ${item.page_number}`);
  }
  const typeLabel = sourceTypeLabel(item.source_type);
  if (typeLabel) parts.push(typeLabel);
  return parts.join(" · ") || "Vị trí nguồn không có";
}

export function allEvidenceItems(clause: ContractClauseResult): ContractEvidenceRef[] {
  if (Array.isArray(clause.evidence)) return clause.evidence;
  return Array.isArray(clause.citations) ? clause.citations : [];
}

export function versionGroupLabel(side: EvidenceVersionGroup): string {
  if (side === "v1") return "Phiên bản 1";
  if (side === "v2") return "Phiên bản 2";
  return "Nguồn";
}

export function hasSourceSpan(item: ContractEvidenceRef): boolean {
  return (
    typeof item.start_offset === "number" &&
    typeof item.end_offset === "number" &&
    item.end_offset > item.start_offset
  );
}

export function itemVerificationNote(
  clause: ContractClauseResult,
  item: ContractEvidenceRef,
): string | null {
  const id = item.evidence_id ? String(item.evidence_id) : null;
  if (!id) return null;
  const rows = clause.verification?.evidence_results ?? [];
  const match = rows.find((row) => row.evidence_id === id);
  const reasons = (match?.reasons ?? [])
    .map((reason) => String(reason ?? "").trim())
    .filter(Boolean);
  return reasons.length ? reasons.join(" ") : null;
}

export function sourceMetadataLines(
  item: ContractEvidenceRef,
  versionLabel: string,
  documentTitle?: string | null,
): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  const title = (documentTitle ?? "").trim();
  if (title) rows.push({ label: "Tài liệu", value: title });
  rows.push({ label: "Phiên bản", value: versionLabel });
  if (typeof item.page_number === "number" && item.page_number > 0) {
    rows.push({ label: "Trang", value: String(item.page_number) });
  }
  if (item.clause_id) {
    rows.push({ label: "Điều khoản", value: displayClauseId(item.clause_id) });
  }
  const typeLabel = sourceTypeLabel(item.source_type);
  if (typeLabel) rows.push({ label: "Loại", value: typeLabel });
  return rows;
}

export function buildEvidenceSourceHref(
  workspaceId: string,
  evidence: ContractEvidenceRef,
  fallbackDocumentId?: string | null,
  fallbackVersionId?: string | null,
): string | null {
  const href = evidenceViewerHref(
    workspaceId,
    evidence,
    fallbackDocumentId,
    fallbackVersionId,
  );
  if (!href) return null;
  const citationId = (evidence.evidence_id ?? "").trim();
  if (!citationId) return href;
  const join = href.includes("?") ? "&" : "?";
  return `${href}${join}citation=${encodeURIComponent(citationId)}`;
}

export function aiCitationRefs(clause: ContractClauseResult): {
  index: number;
  evidenceId: string;
  item: EvidenceListItem | null;
}[] {
  const items = flattenEvidenceItems(clause);
  return aiEvidenceIds(clause).map((evidenceId, index) => ({
    index: index + 1,
    evidenceId,
    item: items.find((row) => row.evidence.evidence_id === evidenceId) ?? null,
  }));
}

export function groupedEvidence(
  clause: ContractClauseResult,
): { v1: EvidenceListItem[]; v2: EvidenceListItem[]; other: EvidenceListItem[] } {
  const groups: {
    v1: EvidenceListItem[];
    v2: EvidenceListItem[];
    other: EvidenceListItem[];
  } = { v1: [], v2: [], other: [] };
  allEvidenceItems(clause).forEach((evidence, index) => {
    const side = evidenceSide(evidence);
    const item: EvidenceListItem = {
      key: `${evidence.evidence_id || "ev"}-${side}-${index}`,
      evidence,
      side,
      verification: itemVerificationState(clause, evidence),
      primary: isPrimaryEvidence(evidence),
      excerpt: evidenceExcerpt(evidence, clause),
      locationLabel: sourceLocationLabel(evidence),
    };
    groups[side].push(item);
  });
  return groups;
}

export function flattenEvidenceItems(clause: ContractClauseResult): EvidenceListItem[] {
  const groups = groupedEvidence(clause);
  return [...groups.v1, ...groups.v2, ...groups.other];
}

export function findingContext(clause: ContractClauseResult): string {
  const diffs = clause.exact_differences ?? [];
  if (diffs.length > 0) {
    const first = formatExactDifference(diffs[0]);
    if (first.oldDisplay !== "—" || first.newDisplay !== "—") {
      return `${first.label}: ${first.oldDisplay} → ${first.newDisplay}`;
    }
  }
  return shortChangeSummary(clause);
}

export function aiEvidenceIds(clause: ContractClauseResult): string[] {
  const ids = clause.explanation?.output?.evidence_ids;
  if (!Array.isArray(ids)) return [];
  return ids.map((id) => String(id).trim()).filter(Boolean);
}

export function verificationMessage(clause: ContractClauseResult): string | null {
  const text = (clause.verification?.human_message ?? "").trim();
  return text || null;
}

export function absenceStatus(clause: ContractClauseResult, side: "v1" | "v2"): string | null {
  const status = String(clause.status).toUpperCase();
  const absence = String(clause.verification?.absence_status ?? "").toUpperCase();
  if (status === "ADDED" && side === "v1") {
    if (absence === "ABSENCE_CONFIRMED") {
      return "Nguồn xác nhận không có điều khoản tương ứng ở V1.";
    }
    return absenceMessage(status, "v1");
  }
  if (status === "REMOVED" && side === "v2") {
    if (absence === "ABSENCE_CONFIRMED") {
      return "Nguồn xác nhận không có điều khoản tương ứng ở V2.";
    }
    return absenceMessage(status, "v2");
  }
  if (absence === "INSUFFICIENT_EVIDENCE") {
    return side === "v1"
      ? "Chưa đủ bằng chứng để xác định điều khoản tương ứng không tồn tại trong V1."
      : "Chưa đủ bằng chứng để xác định điều khoản tương ứng không tồn tại trong V2.";
  }
  return null;
}

export function copyCitationText(
  item: EvidenceListItem,
  versionLabel: string,
): string {
  const lines = [
    item.locationLabel,
    versionLabel,
    item.excerpt,
  ].filter(Boolean);
  return lines.join("\n");
}

export function evidenceCountLabel(count: number): string {
  if (count === 1) return "1 nguồn";
  return `${count} nguồn`;
}

export function documentTitleForSide(
  report: ContractComparisonReport | null,
  side: EvidenceVersionGroup,
  documentMeta?: Record<string, { title: string }>,
): string | null {
  const ref = side === "v2" ? report?.metadata?.document_v2 : report?.metadata?.document_v1;
  const id = ref?.document_id ?? "";
  return documentMeta?.[id]?.title ?? ref?.title ?? null;
}

export function fallbackDocumentForSide(
  report: ContractComparisonReport | null,
  side: EvidenceVersionGroup,
): { documentId: string | null; versionId: string | null } {
  const ref = side === "v2" ? report?.metadata?.document_v2 : report?.metadata?.document_v1;
  return {
    documentId: ref?.document_id ?? null,
    versionId: ref?.document_version_id ?? null,
  };
}
