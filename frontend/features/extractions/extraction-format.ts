/**
 * =============================================================================
 * File: extraction-format.ts
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for Extraction labels, selection, export, copy (FR7).
 * Responsibilities:
 *   - Type/format labels; getCurrentExtraction selection algorithm
 *   - Table payload narrowing; CSV/JSON export builders; copy text
 * Dependencies:
 *   - types/extractions, lib/download
 * Public Exports:
 *   - EXTRACTION_TYPE_OPTIONS, OUTPUT_FORMAT_OPTIONS, getCurrentExtraction,
 *     getProcessingExtraction, getFailedExtraction, isOldVersion,
 *     asTablePayload, buildExportFilename, buildCopyText, …
 * Database/Table: N/A
 * Related Modules: features/extractions/*, scripts/test-extraction-ui.mjs
 * Important Notes: Selection never picks an old-version extraction as current.
 *   FE does not sort timeline / infer columns — backend owns semantics.
 * =============================================================================
 */

import { serializeToCsv } from "@/lib/download";
import type {
  Extraction,
  ExtractionOutputFormat,
  ExtractionStatus,
  ExtractionType,
  TableResultPayload,
} from "@/types/extractions";

export const EXTRACTION_TYPE_OPTIONS: ReadonlyArray<{
  type: ExtractionType;
  label: string;
}> = [
  { type: "table", label: "Bảng" },
  { type: "figures", label: "Số liệu" },
  { type: "entities", label: "Thực thể" },
  { type: "timeline", label: "Mốc thời gian" },
];

export const OUTPUT_FORMAT_OPTIONS: ReadonlyArray<{
  format: ExtractionOutputFormat;
  label: string;
}> = [
  { format: "json", label: "JSON" },
  { format: "table", label: "Bảng" },
];

export function typeLabel(type: ExtractionType): string {
  return EXTRACTION_TYPE_OPTIONS.find((o) => o.type === type)?.label ?? type;
}

export function formatLabel(format: ExtractionOutputFormat): string {
  return OUTPUT_FORMAT_OPTIONS.find((o) => o.format === format)?.label ?? format;
}

export function statusLabel(status: ExtractionStatus): string {
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
  extraction: Pick<Extraction, "source_version_id">,
  currentVersionId: string | null,
): boolean {
  if (!currentVersionId) return false;
  return extraction.source_version_id !== currentVersionId;
}

/**
 * Selection priority:
 * 1. completed
 * 2. matching extraction_type
 * 3. matching output_format
 * 4. matching current_version_id
 * 5. newest created_at
 */
export function getCurrentExtraction(
  extractions: readonly Extraction[],
  currentVersionId: string | null,
  extractionType: ExtractionType,
  outputFormat: ExtractionOutputFormat,
): Extraction | null {
  if (!currentVersionId) return null;
  const matches = extractions.filter(
    (e) =>
      e.status === "completed" &&
      e.extraction_type === extractionType &&
      e.output_format === outputFormat &&
      e.source_version_id === currentVersionId,
  );
  if (matches.length === 0) return null;
  return [...matches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
}

export function getProcessingExtraction(
  extractions: readonly Extraction[],
  currentVersionId: string | null,
  extractionType: ExtractionType,
  outputFormat: ExtractionOutputFormat,
): Extraction | null {
  if (!currentVersionId) return null;
  const matches = extractions.filter(
    (e) =>
      e.status === "processing" &&
      e.extraction_type === extractionType &&
      e.output_format === outputFormat &&
      e.source_version_id === currentVersionId,
  );
  if (matches.length === 0) return null;
  return [...matches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
}

export function getFailedExtraction(
  extractions: readonly Extraction[],
  currentVersionId: string | null,
  extractionType: ExtractionType,
  outputFormat: ExtractionOutputFormat,
): Extraction | null {
  if (!currentVersionId) return null;
  const matches = extractions.filter(
    (e) =>
      e.status === "failed" &&
      e.extraction_type === extractionType &&
      e.output_format === outputFormat &&
      e.source_version_id === currentVersionId,
  );
  if (matches.length === 0) return null;
  return [...matches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
}

export function formatExtractionDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function asTablePayload(
  result: Extraction["result"],
): TableResultPayload | null {
  if (!result || typeof result !== "object") return null;
  const headers = (result as TableResultPayload).headers;
  const rows = (result as TableResultPayload).rows;
  if (!Array.isArray(headers) || !Array.isArray(rows)) return null;
  return {
    headers: headers.map((h) => String(h)),
    rows: rows as Array<Record<string, unknown>>,
  };
}

export function isEmptyTable(payload: TableResultPayload): boolean {
  return payload.headers.length === 0 || payload.rows.length === 0;
}

export function buildExportFilename(
  documentId: string,
  extractionType: ExtractionType,
  extension: "csv" | "json",
  when: Date = new Date(),
): string {
  const stamp = when.toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `document-${documentId.slice(0, 8)}-${extractionType}-${stamp}.${extension}`;
}

export function buildCsvFromExtraction(extraction: Extraction): string | null {
  const table = asTablePayload(extraction.result);
  if (!table || isEmptyTable(table)) return null;
  return serializeToCsv(table.headers, table.rows);
}

export function buildJsonExport(extraction: Extraction): string | null {
  if (extraction.result == null) return null;
  return `${JSON.stringify(extraction.result, null, 2)}\n`;
}

export function buildCopyText(extraction: Extraction): string {
  if (extraction.result == null) return "";
  if (extraction.output_format === "table") {
    const table = asTablePayload(extraction.result);
    if (!table) return JSON.stringify(extraction.result, null, 2);
    const lines = [table.headers.join("\t")];
    for (const row of table.rows) {
      lines.push(table.headers.map((h) => String(row[h] ?? "")).join("\t"));
    }
    return lines.join("\n");
  }
  return JSON.stringify(extraction.result, null, 2);
}
