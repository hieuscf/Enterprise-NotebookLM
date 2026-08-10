/**
 * =============================================================================
 * File: admin-documents.ts
 * Module/Service: Admin Document Management (Web App) — FR2 / FR12
 * Layer: UI
 * Purpose: Pure helpers for `/admin/documents` — labels, size/time formatting,
 *          status presentation (not color-only).
 * Responsibilities:
 *   - Map DocumentVersion.status → accessible label + icon marker
 *   - Human-readable file size / relative updated time
 * Dependencies:
 *   - types/documents
 * Public Exports:
 *   - VERSION_STATUS_LABEL, formatAdminFileSize, formatRelativeUpdated,
 *     FILE_TYPE_LABEL
 * Database/Table: N/A
 * Related Modules: features/admin/AdminDocumentsTable
 * Important Notes: Status vocabulary is processing|ready|failed (version enum).
 * =============================================================================
 */

import type { DocumentVersionStatus, FileType } from "@/types/documents";

export const VERSION_STATUS_LABEL: Record<DocumentVersionStatus, string> = {
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

/** Compact marker used beside status text (accessible label is separate). */
export const VERSION_STATUS_MARKER: Record<DocumentVersionStatus, string> = {
  processing: "●",
  ready: "✓",
  failed: "!",
};

export const VERSION_STATUS_CLASS: Record<DocumentVersionStatus, string> = {
  processing: "text-warning",
  ready: "text-success",
  failed: "text-danger",
};

export const FILE_TYPE_LABEL: Record<FileType, string> = {
  pdf: "PDF",
  docx: "DOCX",
  xlsx: "XLSX",
  pptx: "PPTX",
  txt: "TXT",
};

export function formatAdminFileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) {
    const kb = bytes / 1024;
    return `${kb >= 100 ? kb.toFixed(0) : kb.toFixed(1)} KB`;
  }
  const mb = bytes / (1024 * 1024);
  return `${mb >= 100 ? mb.toFixed(0) : mb.toFixed(1)} MB`;
}

export function formatRelativeUpdated(iso: string, now = new Date()): string {
  try {
    const date = new Date(iso);
    const diffMs = now.getTime() - date.getTime();
    if (!Number.isFinite(diffMs)) return iso;

    const abs = Math.abs(diffMs);
    if (abs < 60_000) return "Just now";
    if (abs < 3_600_000) {
      const mins = Math.round(abs / 60_000);
      return `${mins} min ago`;
    }

    const sameDay =
      date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate();
    if (sameDay) {
      return `Today, ${new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(date)}`;
    }

    if (abs < 7 * 24 * 3_600_000) {
      return new Intl.DateTimeFormat("en-US", {
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(date);
    }

    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
  } catch {
    return iso;
  }
}

export function formatFullTimestamp(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "medium",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
