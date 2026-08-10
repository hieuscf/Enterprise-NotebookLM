/**
 * =============================================================================
 * File: documents.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Document/Version/Pipeline matching OpenAPI (FR2).
 * Responsibilities:
 *   - Align frontend Document/DocumentVersion/PipelineRun with backend Pydantic
 *     schemas (app/schemas/documents.py)
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml
 * Public Exports:
 *   - Document, DocumentListResponse, DocumentVersion, DocumentVersionStatus
 *   - PipelineRun, PipelineStageLog, PipelineStageName, PipelineStatus
 * Database/Table: documents, document_versions, pipeline_runs, pipeline_stage_logs
 * Related Modules: lib/api-client, lib/pipeline-stages, features/documents/*
 * Important Notes: PipelineStageName includes legacy v2 values (ocr_cleaning,
 *   chunking) returned by old runs — v3 UI only renders PIPELINE_STAGE_ORDER (6).
 * =============================================================================
 */

export type FileType = "pdf" | "docx" | "xlsx" | "pptx" | "txt";

export type Document = {
  id: string;
  workspace_id: string;
  title: string;
  file_type: FileType;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentListResponse = {
  items: Document[];
  page: number;
  page_size: number;
  total: number;
};

export type DocumentChunk = {
  id: string;
  document_id: string;
  document_version_id: string;
  chunk_index: number;
  content: string;
  page_number?: number | null;
  section_index?: number | null;
  section?: string | null;
  heading_path?: string | null;
  section_path?: string | null;
  bounding_box?: number[] | null;
  start_offset?: number | null;
  end_offset?: number | null;
};

export type DocumentChunkListResponse = {
  document_id: string;
  document_version_id: string | null;
  document_title: string;
  file_type: FileType;
  viewer_kind?: "pdf" | "original_download";
  preview_status?: PreviewStatus;
  preview_type?: PreviewType | null;
  preview_generated_at?: string | null;
  heading_tree?: Array<Record<string, unknown>>;
  items: DocumentChunk[];
};

export type DocumentVersionStatus = "processing" | "ready" | "failed";

export type PreviewStatus = "pending" | "processing" | "completed" | "failed";
export type PreviewType = "pdf" | "html" | "image";

export type DocumentVersion = {
  id: string;
  document_id: string;
  uploaded_by: string;
  version_number: number;
  file_size_bytes: number;
  checksum_sha256: string;
  page_count: number | null;
  status: DocumentVersionStatus;
  is_current: boolean;
  created_at: string;
  preview_status?: PreviewStatus;
  preview_type?: PreviewType | null;
  preview_generated_at?: string | null;
};

/** v3 stage order including Preview Generation before AI stages. */
export type PipelineStageNameV3 =
  | "preview_generation"
  | "document_understanding"
  | "cleaning_normalize"
  | "hierarchical_chunking"
  | "embedding"
  | "graph_extraction"
  | "indexing";

/** Legacy v2 stages a run can still report; not part of the 6-step v3 tracker UI. */
export type PipelineStageNameLegacy = "ocr_cleaning" | "chunking";

export type PipelineStageName = PipelineStageNameV3 | PipelineStageNameLegacy;

export type PipelineStatus = "pending" | "running" | "completed" | "failed";

export type PipelineStageLog = {
  id: string;
  stage: PipelineStageName;
  status: PipelineStatus;
  duration_ms: number | null;
  metadata: Record<string, unknown> | null;
  error_message: string | null;
};

export type PipelineRun = {
  id: string;
  document_version_id: string;
  status: PipelineStatus;
  retry_count: number;
  error_message: string | null;
  stages: PipelineStageLog[];
  started_at: string | null;
  completed_at: string | null;
  /** Present on admin pipeline-runs list; may be null elsewhere. */
  document_id?: string | null;
  document_title?: string | null;
  file_type?: FileType | null;
  version_number?: number | null;
};
