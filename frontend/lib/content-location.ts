/**
 * =============================================================================
 * File: content-location.ts
 * Module/Service: Citation / Documents UI
 * Layer: UI
 * Purpose: Format ContentLocation + document extent labels (FR5 convention).
 * Responsibilities:
 *   - PDF/PPTX/XLSX → "Trang X"; DOCX → "Mục X" (+ section title)
 *   - Document list page_count: DOCX → "X mục", others → "X trang"
 * Dependencies:
 *   - OpenAPI ContentLocation; Business Context FR5
 * Public Exports:
 *   - ContentLocation, formatContentLocationLabel, formatDocumentExtentLabel
 * Database/Table: N/A
 * Related Modules: features/citation/CitationLocationLabel
 * Important Notes: Never show "Trang X" for DOCX section_index.
 * =============================================================================
 */

export type ContentLocation = {
  page_number?: number | null;
  section_index?: number | null;
  section_title?: string | null;
};

export type DocumentFileType = "pdf" | "docx" | "xlsx" | "pptx" | "txt";

/** Citation chip label; null when no locator (hide position UI). */
export function formatContentLocationLabel(
  location: ContentLocation | null | undefined,
): string | null {
  if (!location) return null;
  if (location.page_number != null) {
    return `Trang ${location.page_number}`;
  }
  if (location.section_index != null) {
    const title = (location.section_title || "").trim();
    return title
      ? `Mục ${location.section_index}: ${title}`
      : `Mục ${location.section_index}`;
  }
  return null;
}

/** Document list extent from page_count + file_type. */
export function formatDocumentExtentLabel(
  fileType: DocumentFileType | string | null | undefined,
  pageCount: number | null | undefined,
): string | null {
  if (pageCount == null || pageCount < 0) return null;
  if (fileType === "docx") {
    return pageCount === 1 ? "1 mục" : `${pageCount} mục`;
  }
  if (fileType === "pptx") {
    return pageCount === 1 ? "1 slide" : `${pageCount} slide`;
  }
  if (fileType === "xlsx") {
    return pageCount === 1 ? "1 sheet" : `${pageCount} sheet`;
  }
  return pageCount === 1 ? "1 trang" : `${pageCount} trang`;
}
