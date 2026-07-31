/**
 * =============================================================================
 * File: search.ts
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types aligned with OpenAPI Search schemas (FR3 / UC3).
 * Responsibilities:
 *   - Define SearchRequest, SearchResultResponse, SearchHistoryItem
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml §SEARCH
 * Public Exports:
 *   - SearchFilters, SearchRequest, SearchResultItem, SearchResultResponse
 *   - SearchHistoryItem, RetrievalMethod
 * Database/Table: N/A
 * Related Modules: lib/search.api.ts, features/search/*
 * Important Notes: Do not add fields beyond OpenAPI without confirmation.
 * =============================================================================
 */

import type { FileType } from "./documents";

export type RetrievalMethod = "vector" | "bm25" | "knowledge_graph" | "rerank";

export type SearchFilters = {
  file_type?: FileType | FileType[] | null;
  date_from?: string | null;
  date_to?: string | null;
  date_range?: { from?: string; to?: string } | null;
  tags?: string[] | null;
};

export type SearchRequest = {
  query_text: string;
  filters?: SearchFilters | null;
  top_k?: number;
};

export type SearchResultItem = {
  chunk_id: string | null;
  entity_id: string | null;
  document_id: string;
  text_snippet: string;
  retrieval_method: RetrievalMethod;
  score: number;
  rank: number;
};

export type SearchResultResponse = {
  history_id: string;
  results_count: number;
  results: SearchResultItem[];
};

export type SearchHistoryClickRequest = {
  clicked_document_id: string;
};

export type SearchHistoryItem = {
  id: string;
  query_text: string;
  filters: SearchFilters | Record<string, unknown> | null;
  results_count: number;
  clicked_document_id: string | null;
  created_at: string;
};
