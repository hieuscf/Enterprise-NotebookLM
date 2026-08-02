/**
 * =============================================================================
 * File: useSearch.ts
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Client hook for running workspace semantic search (FR3 / UC3).
 * Responsibilities:
 *   - Call searchWorkspace; expose loading/error/results/lastQuery
 * Dependencies:
 *   - lib/search.api, types/search
 * Public Exports:
 *   - useSearch
 * Database/Table: N/A
 * Related Modules: features/search/SearchView.tsx
 * Important Notes: Local component state only — no global store.
 * =============================================================================
 */

"use client";

import { useCallback, useState } from "react";

import { ApiClientError } from "@/lib/api-client";
import { searchWorkspace } from "@/lib/search.api";
import { filterResultsByMinScore } from "@/lib/search-score";
import type {
  SearchFilters,
  SearchResultItem,
  SearchResultResponse,
} from "@/types/search";

export function useSearch(workspaceId: string) {
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [resultsCount, setResultsCount] = useState(0);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const runSearch = useCallback(
    async (queryText: string, filters?: SearchFilters | null, topK = 10) => {
      const q = queryText.trim();
      if (!q) {
        setError("Nhập từ khóa để tìm kiếm.");
        return null;
      }
      setLoading(true);
      setError(null);
      setLastQuery(q);
      setHasSearched(true);
      try {
        const data: SearchResultResponse = await searchWorkspace(workspaceId, {
          query_text: q,
          filters: filters ?? undefined,
          top_k: topK,
        });
        // Defense-in-depth: only show hits with score >= 0.6 (backend also filters).
        const filtered = filterResultsByMinScore(data.results);
        setResults(filtered);
        setResultsCount(filtered.length);
        setHistoryId(data.history_id);
        return { ...data, results: filtered, results_count: filtered.length };
      } catch (err) {
        setResults([]);
        setResultsCount(0);
        setHistoryId(null);
        setError(
          err instanceof ApiClientError
            ? err.message
            : "Không thực hiện được tìm kiếm. Thử lại sau.",
        );
        return null;
      } finally {
        setLoading(false);
      }
    },
    [workspaceId],
  );

  return {
    results,
    resultsCount,
    historyId,
    lastQuery,
    loading,
    error,
    hasSearched,
    runSearch,
  };
}
