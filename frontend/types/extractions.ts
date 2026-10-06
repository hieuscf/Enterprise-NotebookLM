/**
 * =============================================================================
 * File: extractions.ts
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Extractions API matching OpenAPI (FR7).
 * Responsibilities:
 *   - Align Extraction / ExtractionType / OutputFormat / Status with backend
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml Extraction schema
 * Public Exports:
 *   - ExtractionType, ExtractionOutputFormat, ExtractionStatus, TargetLanguage,
 *     Extraction, ExtractionCreateRequest, TableResultPayload, DocumentTableItem,
 *     TableGalleryPayload
 * Database/Table: extractions
 * Related Modules: lib/extractions.api, features/extractions/*
 * Important Notes: result is null while processing/failed; structured when completed.
 *   extraction_type=table → gallery {tables:[...]}. Cost/token fields are not public.
 * =============================================================================
 */

export type ExtractionType = "table" | "figures" | "entities" | "timeline";

export type ExtractionOutputFormat = "json" | "table";

export type ExtractionStatus = "processing" | "completed" | "failed";

export type TargetLanguage = "vi" | "en";

/** Shared table-ready shape for non-table types with output_format=table. */
export type TableResultPayload = {
  headers: string[];
  rows: Array<Record<string, unknown>>;
};

/** One original document table in extraction_type=table gallery. */
export type DocumentTableItem = {
  id: string;
  title: string;
  source_chunk_id: string;
  page_number?: number | null;
  heading_path?: string | null;
  headers: string[];
  rows: Array<Record<string, unknown>>;
};

export type TableGalleryPayload = {
  tables: DocumentTableItem[];
};

export type Extraction = {
  id: string;
  document_id: string;
  source_version_id: string;
  extraction_type: ExtractionType;
  output_format: ExtractionOutputFormat;
  target_language: TargetLanguage;
  status: ExtractionStatus;
  result: Record<string, unknown> | TableResultPayload | TableGalleryPayload | null;
  created_at: string;
};

export type ExtractionCreateRequest = {
  extraction_type: ExtractionType;
  output_format?: ExtractionOutputFormat;
  target_language?: TargetLanguage;
};
