/**
 * =============================================================================
 * File: useAdminQueryLogs.ts
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Load the most recent query_logs rows for the Recent Query Activity
 *          table (GET /admin/workspaces/{id}/query-logs).
 * Responsibilities:
 *   - Fetch newest-first page; expose loading/error/reload independent from
 *     other dashboard sections
 * Dependencies:
 *   - lib/admin.api.listWorkspaceQueryLogs
 * Public Exports:
 *   - useAdminQueryLogs
 * Database/Table: query_logs
 * Related Modules: features/admin/RecentQueriesTable
 * Important Notes: No date-range filter exists on this endpoint — this is an
 *   activity feed (latest N), independent of the KPI period selector.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { listWorkspaceQueryLogs } from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import type { QueryLogItem } from "@/types/admin";

export function useAdminQueryLogs(workspaceId: string | null, pageSize = 8) {
  const [items, setItems] = useState<QueryLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkspaceQueryLogs(workspaceId, { page: 1, pageSize });
      setItems(data);
    } catch (err) {
      setItems([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được nhật ký truy vấn gần đây.",
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
