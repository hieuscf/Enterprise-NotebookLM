/**
 * =============================================================================
 * File: useWorkspaces.ts
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Client hook to load / refresh the current user's workspace list.
 * Responsibilities:
 *   - Fetch GET /workspaces via BFF; expose loading / error / reload
 * Dependencies:
 *   - lib/api-client.listWorkspaces
 * Public Exports:
 *   - useWorkspaces
 * Database/Table: N/A
 * Related Modules: features/workspaces, types/workspaces
 * Important Notes: Soft-deleted workspaces are already filtered by the API.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiClientError, listWorkspaces } from "@/lib/api-client";
import type { Workspace } from "@/types/workspaces";

export function useWorkspaces(page = 1, pageSize = 20) {
  const [items, setItems] = useState<Workspace[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkspaces(page, pageSize);
      setItems(data.items);
      setTotal(data.total);
      return data;
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : "Không tải được danh sách workspace.";
      setError(message);
      setItems([]);
      setTotal(0);
      return null;
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { items, total, page, pageSize, loading, error, reload };
}
