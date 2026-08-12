/**
 * =============================================================================
 * File: citation-types.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Frontend view-model for citations used by Research Workspace UI.
 * Responsibilities:
 *   - Define CitationViewModel enriched for chips / source panel / document open
 * Dependencies:
 *   - types/citations, lib/content-location
 * Public Exports:
 *   - CitationViewModel, SourceDocumentGroup
 * Database/Table: N/A
 * Related Modules: citation-mapper, SourcePanel, CitationChip
 * Important Notes: API Citation has no document_title — enrichment is client-side.
 * =============================================================================
 */

import type { ContentLocation } from "@/lib/content-location";
import type { FileType } from "@/types/documents";

/** UI-facing citation after mapping + document title enrichment. */
export type CitationViewModel = {
  id: string;
  messageId: string;
  retrievalId: string;
  documentId: string;
  documentVersionId?: string;
  documentTitle: string;
  fileType?: FileType | string;
  page?: number | null;
  sectionIndex?: number | null;
  sectionTitle?: string | null;
  location?: ContentLocation | null;
  textSnippet: string;
  verified: boolean;
  orderIndex: number;
  /** 1-based display index matching inline [n] markers. */
  displayIndex: number;
  /** True when document metadata could not be resolved. */
  documentMissing?: boolean;
};

export type SourceDocumentGroup = {
  documentId: string;
  documentTitle: string;
  fileType?: FileType | string;
  documentMissing?: boolean;
  citations: CitationViewModel[];
  /** Unique page numbers across citations in this group (sorted). */
  pages: number[];
};
