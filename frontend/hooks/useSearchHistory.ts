/**
 * =============================================================================
 * File: useSearchHistory.ts
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Client hook for current-user search history (FR3 / UC3).
 * Responsibilities:
 *   - Load GET .../search/history; expose reload
 * Dependencies:
 *   - lib/search.api.listSearchHistory
 * Public Exports:
 *   - useSearchHistory
 * Database/Table: N/A
 * Related Modules: features/search/SearchHistoryPanel.tsx
 * Important Notes: Backend already scopes to the authenticated user.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiClientError } from "@/lib/api-client";
import { listSearchHistory } from "@/lib/search.api";
import type { SearchHistoryItem } from "@/types/search";

export function useSearchHistory(workspaceId: string, pageSize = 20) {
  const [items, setItems] = useState<SearchHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSearchHistory(workspaceId, { page: 1, pageSize });
      setItems(data);
    } catch (err) {
      setItems([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được lịch sử tìm kiếm.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId, pageSize]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { items, loading, error, reload };
}
