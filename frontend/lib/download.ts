/**
 * =============================================================================
 * File: download.ts
 * Module/Service: Web App shared utilities
 * Layer: UI
 * Purpose: Browser Blob download + CSV serialization helpers.
 * Responsibilities:
 *   - downloadBlob / downloadTextFile
 *   - serializeToCsv (RFC4180-style escaping)
 * Dependencies:
 *   - Browser DOM only
 * Public Exports:
 *   - downloadBlob, downloadTextFile, serializeToCsv, escapeCsvCell
 * Database/Table: N/A
 * Related Modules: features/extractions (FR7 export)
 * Important Notes: No DOM scraping — callers pass structured headers/rows.
 * =============================================================================
 */

export function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "string" ? value : String(value);
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function serializeToCsv(
  headers: readonly string[],
  rows: ReadonlyArray<Record<string, unknown>>,
): string {
  const lines: string[] = [headers.map(escapeCsvCell).join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => escapeCsvCell(row[h])).join(","));
  }
  return lines.join("\r\n");
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function downloadTextFile(
  content: string,
  filename: string,
  mimeType: string,
): void {
  downloadBlob(new Blob([content], { type: mimeType }), filename);
}
