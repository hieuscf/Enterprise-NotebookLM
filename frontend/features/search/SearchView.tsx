/**
 * =============================================================================
 * File: SearchView.tsx
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Compose Search Form / Results / History for a workspace (UC3).
 * Responsibilities:
 *   - Own local search + history state; hydrate document titles for results
 * Dependencies:
 *   - AppShell, SearchForm, SearchResults, SearchHistoryPanel, hooks
 * Public Exports:
 *   - SearchView
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/search/page.tsx
 * Important Notes: Click tracking via PATCH history (fire-and-forget; C+A).
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { SearchFormWithQuery, type SearchFormValues } from "@/features/search/SearchForm";
import { SearchHistoryPanel } from "@/features/search/SearchHistoryPanel";
import { SearchResults } from "@/features/search/SearchResults";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useSearch } from "@/hooks/useSearch";
import { useSearchHistory } from "@/hooks/useSearchHistory";
import { getDocument } from "@/lib/api-client";
import { recordSearchHistoryClick } from "@/lib/search.api";
import type { SearchFilters, SearchResultItem } from "@/types/search";

type Props = {
  workspaceId: string;
};

export function SearchView({ workspaceId }: Props) {
  const { user } = useAuth();
  const {
    results,
    resultsCount,
    historyId,
    lastQuery,
    loading,
    error,
    hasSearched,
    runSearch,
  } = useSearch(workspaceId);
  const history = useSearchHistory(workspaceId);
  const [formKey, setFormKey] = useState("");
  const [titles, setTitles] = useState<Record<string, string>>({});

  const documentIds = useMemo(
    () => Array.from(new Set(results.map((r) => r.document_id))),
    [results],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadTitles() {
      const missing = documentIds.filter((id) => !titles[id]);
      if (!missing.length) return;
      const entries = await Promise.all(
        missing.map(async (id) => {
          try {
            const doc = await getDocument(workspaceId, id);
            return [id, doc.title] as const;
          } catch {
            return [id, `Tài liệu ${id.slice(0, 8)}…`] as const;
          }
        }),
      );
      if (cancelled) return;
      setTitles((prev) => {
        const next = { ...prev };
        for (const [id, title] of entries) next[id] = title;
        return next;
      });
    }
    void loadTitles();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only refetch for new ids
  }, [documentIds, workspaceId]);

  const handleSubmit = useCallback(
    async (values: SearchFormValues) => {
      await runSearch(values.queryText, values.filters);
      void history.reload();
    },
    [runSearch, history],
  );

  const handleReplay = useCallback(
    async (queryText: string, filters?: SearchFilters | null) => {
      setFormKey(queryText);
      await runSearch(queryText, filters ?? null);
      void history.reload();
    },
    [runSearch, history],
  );

  const handleResultClick = useCallback(
    async (item: SearchResultItem) => {
      if (!historyId) return;
      // Fire-and-forget from SearchResults — failures must not block navigation.
      await recordSearchHistoryClick(workspaceId, historyId, item.document_id);
    },
    [historyId, workspaceId],
  );

  return (
    <AppShell active="search" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
        <div>
          <p className="text-caption font-medium text-accent-primary">FR3 · Intelligent Search</p>
          <h1 className="mt-1 text-h1 text-primary">Tìm kiếm</h1>
          <p className="mt-1 text-body-sm text-secondary">
            Hybrid Retrieval (Vector + BM25 + Knowledge Graph) với re-ranking trong workspace này.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="flex min-w-0 flex-col gap-4">
            <SearchFormWithQuery
              queryKey={formKey}
              loading={loading}
              onSubmit={(v) => void handleSubmit(v)}
            />
            <SearchResults
              workspaceId={workspaceId}
              query={lastQuery}
              results={results}
              resultsCount={resultsCount}
              loading={loading}
              error={error}
              hasSearched={hasSearched}
              titles={titles}
              onResultClick={handleResultClick}
            />
          </div>
          <SearchHistoryPanel
            items={history.items}
            loading={history.loading}
            error={history.error}
            onReplay={(q, f) => void handleReplay(q, f)}
          />
        </div>
      </div>
    </AppShell>
  );
}
