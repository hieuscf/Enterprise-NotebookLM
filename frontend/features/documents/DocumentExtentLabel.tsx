/**
 * =============================================================================
 * File: DocumentExtentLabel.tsx
 * Module/Service: Documents UI
 * Layer: UI
 * Purpose: Show document extent using FR5 convention (trang vs mục).
 * Responsibilities:
 *   - DOCX page_count → "X mục"; PDF → "X trang"; PPTX/XLSX → slide/sheet
 * Dependencies:
 *   - lib/content-location
 * Public Exports:
 *   - DocumentExtentLabel
 * Database/Table: document_versions.page_count
 * Related Modules: Business Context FR5; DocumentVersion.page_count
 * Important Notes: DOCX page_count is logical section count from OCR.
 * =============================================================================
 */

import {
  formatDocumentExtentLabel,
  type DocumentFileType,
} from "@/lib/content-location";

type Props = {
  fileType: DocumentFileType | string;
  pageCount: number | null | undefined;
  className?: string;
};

export function DocumentExtentLabel({ fileType, pageCount, className }: Props) {
  const label = formatDocumentExtentLabel(fileType, pageCount);
  if (!label) return null;
  return (
    <span className={className} data-testid="document-extent">
      {label}
    </span>
  );
}
