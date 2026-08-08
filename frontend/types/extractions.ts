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
 *   - ExtractionType, ExtractionOutputFormat, ExtractionStatus, Extraction,
 *     ExtractionCreateRequest, TableResultPayload
 * Database/Table: extractions
 * Related Modules: lib/extractions.api, features/extractions/*
 * Important Notes: result is null while processing/failed; structured when completed.
 *   Cost/token fields are not public API.
 * =============================================================================
 */

export type ExtractionType = "table" | "figures" | "entities" | "timeline";

export type ExtractionOutputFormat = "json" | "table";

export type ExtractionStatus = "processing" | "completed" | "failed";

/** Shared table-ready shape for output_format=table (headers + rows). */
export type TableResultPayload = {
  headers: string[];
  rows: Array<Record<string, unknown>>;
};

export type Extraction = {
  id: string;
  document_id: string;
  source_version_id: string;
  extraction_type: ExtractionType;
  output_format: ExtractionOutputFormat;
  status: ExtractionStatus;
  result: Record<string, unknown> | TableResultPayload | null;
  created_at: string;
};

export type ExtractionCreateRequest = {
  extraction_type: ExtractionType;
  output_format?: ExtractionOutputFormat;
};
