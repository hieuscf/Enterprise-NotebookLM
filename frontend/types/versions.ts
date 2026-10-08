/**
 * =============================================================================
 * File: versions.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Types for the workspace version catalog and edit history.
 * Responsibilities:
 *   - Match VersionCatalogResponse and VersionEventListResponse
 * Dependencies:
 *   - types/documents
 * Public Exports:
 *   - VersionCatalogItem, VersionCatalogResponse, VersionEvent, VersionEventListResponse
 *   - VersionEventType, VersionClassificationInput
 * Database/Table: document_versions, document_version_events
 * Related Modules: lib/api-client, features/versions/VersionCenterView
 * Important Notes: classification_metadata values are strings.
 * =============================================================================
 */

import type { AiAnalysisStatus, DocumentVersionStatus, FileType } from "@/types/documents";

export type VersionEventType = "uploaded" | "rolled_back" | "tags_updated" | "metadata_updated";

export type VersionCatalogItem = {
  id: string;
  document_id: string;
  document_title: string;
  file_type: FileType;
  uploaded_by: string;
  uploader_name: string | null;
  uploader_email: string | null;
  version_number: number;
  file_size_bytes: number;
  checksum_sha256: string;
  page_count: number | null;
  status: DocumentVersionStatus;
  ai_analysis_status: AiAnalysisStatus;
  analyzed_at: string | null;
  is_current: boolean;
  created_at: string;
  change_note: string | null;
  tags: string[];
  classification_metadata: Record<string, string>;
};

export type VersionCatalogResponse = {
  items: VersionCatalogItem[];
  page: number;
  page_size: number;
  total: number;
  available_tags: string[];
};

export type VersionEvent = {
  id: string;
  document_id: string;
  document_version_id: string;
  document_title: string;
  version_number: number;
  actor_id: string;
  actor_name: string | null;
  event_type: VersionEventType;
  summary: string;
  payload: Record<string, unknown> | null;
  created_at: string;
};

export type VersionEventListResponse = {
  items: VersionEvent[];
  page: number;
  page_size: number;
  total: number;
};

export type VersionClassificationInput = {
  tags?: string[];
  classification_metadata?: Record<string, string>;
  change_note?: string | null;
};
