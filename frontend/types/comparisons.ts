/**
 * =============================================================================
 * File: comparisons.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Comparisons API matching OpenAPI (FR8 / UC7).
 * Responsibilities:
 *   - Align Comparison / status / result with backend schema
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml Comparison schema
 * Public Exports:
 *   - ComparisonStatus, ComparisonResult, Comparison, ComparisonCreateRequest
 * Database/Table: comparisons, comparison_documents
 * Related Modules: lib/comparisons.api, features/comparisons/*
 * Important Notes: result is null while processing/failed; object when completed.
 * =============================================================================
 */

export type ComparisonStatus = "processing" | "completed" | "failed";

export type ComparisonResult = {
  similarities: string[];
  differences: string[];
};

export type Comparison = {
  id: string;
  workspace_id: string;
  document_ids: string[];
  status: ComparisonStatus;
  result: ComparisonResult | null;
  created_at: string;
};

export type ComparisonCreateRequest = {
  document_ids: string[];
  focus?: string | null;
};
