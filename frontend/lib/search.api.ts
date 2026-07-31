/**
 * =============================================================================
 * File: search.api.ts
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: API client for Intelligent Search + history (FR3 / UC3).
 * Responsibilities:
 *   - POST search; GET history; PATCH history click (fire-and-forget from UI)
 * Dependencies:
 *   - lib/api-client.apiFetch/parseApiError
 * Public Exports:
 *   - searchWorkspace, listSearchHistory, recordSearchHistoryClick
 * Database/Table: N/A
 * Related Modules: types/search, features/search/*
 * Important Notes: Click PATCH is idempotent (C+A OpenAPI contract).
 * =============================================================================
 */

import { apiFetch, parseApiError } from "@/lib/api-client";
import type {
  SearchHistoryItem,
  SearchRequest,
  SearchResultResponse,
} from "@/types/search";

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    throw await parseApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function searchWorkspace(
  workspaceId: string,
  body: SearchRequest,
): Promise<SearchResultResponse> {
  return apiJson<SearchResultResponse>(`/workspaces/${workspaceId}/search`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listSearchHistory(
  workspaceId: string,
  options?: { page?: number; pageSize?: number },
): Promise<SearchHistoryItem[]> {
  const params = new URLSearchParams({
    page: String(options?.page ?? 1),
    page_size: String(options?.pageSize ?? 20),
  });
  return apiJson<SearchHistoryItem[]>(
    `/workspaces/${workspaceId}/search/history?${params.toString()}`,
  );
}

export async function recordSearchHistoryClick(
  workspaceId: string,
  historyId: string,
  clickedDocumentId: string,
): Promise<SearchHistoryItem> {
  return apiJson<SearchHistoryItem>(
    `/workspaces/${workspaceId}/search/history/${historyId}`,
    {
      method: "PATCH",
      body: JSON.stringify({ clicked_document_id: clickedDocumentId }),
    },
  );
}
