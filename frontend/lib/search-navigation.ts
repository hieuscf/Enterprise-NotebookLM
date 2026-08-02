/**
 * =============================================================================
 * File: search-navigation.ts
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Build Document Viewer deep-link URLs and persist Search page state.
 * Responsibilities:
 *   - buildDocumentViewerHref(?chunk=&page=); sessionStorage for search restore
 * Dependencies:
 *   - types/search
 * Public Exports:
 *   - buildDocumentViewerHref, saveSearchPageState, loadSearchPageState
 * Database/Table: N/A
 * Related Modules: features/search/SearchResults, SearchView
 * Important Notes: Prefer chunk_id; page is optional hint only.
 * =============================================================================
 */

import type { SearchFilters, SearchResultItem } from "@/types/search";

const SEARCH_STATE_PREFIX = "enlm:search-state:";

export type SearchPageState = {
  queryText: string;
  filters: SearchFilters | null;
  scrollY: number;
  savedAt: number;
};

export function buildDocumentViewerHref(
  workspaceId: string,
  item: Pick<SearchResultItem, "document_id" | "chunk_id" | "page_number" | "location">,
): string {
  const params = new URLSearchParams();
  if (item.chunk_id) {
    params.set("chunk", item.chunk_id);
  }
  const page = item.page_number ?? item.location?.page_number ?? null;
  if (page != null) {
    params.set("page", String(page));
  }
  const qs = params.toString();
  const base = `/workspaces/${workspaceId}/documents/${item.document_id}`;
  return qs ? `${base}?${qs}` : base;
}

export function saveSearchPageState(workspaceId: string, state: SearchPageState): void {
  try {
    sessionStorage.setItem(
      `${SEARCH_STATE_PREFIX}${workspaceId}`,
      JSON.stringify(state),
    );
  } catch {
    /* ignore quota / private mode */
  }
}

export function loadSearchPageState(workspaceId: string): SearchPageState | null {
  try {
    const raw = sessionStorage.getItem(`${SEARCH_STATE_PREFIX}${workspaceId}`);
    if (!raw) return null;
    return JSON.parse(raw) as SearchPageState;
  } catch {
    return null;
  }
}

export function clearSearchPageState(workspaceId: string): void {
  try {
    sessionStorage.removeItem(`${SEARCH_STATE_PREFIX}${workspaceId}`);
  } catch {
    /* ignore */
  }
}
