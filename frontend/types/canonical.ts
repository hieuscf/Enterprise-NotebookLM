/**
 * =============================================================================
 * File: canonical.ts
 * Module/Service: Document Intelligence
 * Layer: UI
 * Purpose: Types for Canonical Knowledge Document + citation locator.
 * Responsibilities:
 *   - Mirror OpenAPI CanonicalDocument / CitationLocator
 * Public Exports:
 *   - CanonicalBlock, CanonicalDocument, CitationLocator, BlockTextRange
 * Database/Table: N/A
 * Related Modules: KnowledgeView, Citation deep-link
 * Important Notes: Knowledge View is primary; Original View uses page/bbox only.
 * =============================================================================
 */

export type BlockTextRange = {
  block_id: string;
  start: number;
  end: number;
};

export type CitationLocator = {
  type: "canonical";
  view: "knowledge";
  confidence: "exact" | "normalized" | "none";
  markdown_start?: number | null;
  markdown_end?: number | null;
  ranges?: BlockTextRange[];
  page_number?: number | null;
  section_index?: number | null;
  bbox?: number[] | null;
};

export type CanonicalBlock = {
  id: string;
  order_index: number;
  block_type: "heading" | "paragraph" | "table" | "list" | "figure";
  content: string;
  heading_path?: string | null;
  heading_level?: number | null;
  depth?: number;
  markdown_start?: number | null;
  markdown_end?: number | null;
  page_number?: number | null;
  section_index?: number | null;
  bbox?: number[] | null;
};

export type CanonicalDocument = {
  document_id: string;
  document_version_id: string;
  document_title: string;
  file_type: "pdf" | "docx" | "xlsx" | "pptx" | "txt";
  markdown: string;
  blocks: CanonicalBlock[];
  heading_tree: Array<Record<string, unknown>>;
  has_original: boolean;
  preview_status: "pending" | "processing" | "completed" | "failed";
};
