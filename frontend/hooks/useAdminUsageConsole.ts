/**
 * =============================================================================
 * File: useAdminUsageConsole.ts
 * Module/Service: Observability Module (Web App) — FR13
 * Layer: UI
 * Purpose: Data hook for `/admin/usage` — CostSummary for a date window.
 * Responsibilities:
 *   - Fetch GET /admin/workspaces/{id}/cost-summary?from&to
 *   - Manual reload only (no polling / fake realtime)
 * Dependencies:
 *   - lib/admin.api.getWorkspaceCostSummary
 * Public Exports:
 *   - useAdminUsageConsole
 * Database/Table: message_generations (via CostSummary)
 * Related Modules: features/admin/AdminUsageView
 * Important Notes: CostSummary API is the source of truth. Do not aggregate
 *   from query-logs. No daily time-series — do not invent trends.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getWorkspaceCostSummary } from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import type { CostSummary } from "@/types/admin";

export type AdminUsageConsoleParams = {
  workspaceId: string | null;
  from: string;
  to: string;
};

export function useAdminUsageConsole({
  workspaceId,
  from,
  to,
}: AdminUsageConsoleParams) {
  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const requestId = useRef(0);

  const reload = useCallback(async () => {
    if (!workspaceId || !from || !to) {
      setSummary(null);
      setLoading(false);
      setError(null);
      return;
    }

    const id = ++requestId.current;
    setLoading(true);
    setError(null);

    try {
      const data = await getWorkspaceCostSummary(workspaceId, { from, to });
      if (id !== requestId.current) return;
      setSummary(data);
      setLastUpdatedAt(Date.now());
    } catch (err) {
      if (id !== requestId.current) return;
      setSummary(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load usage data.",
      );
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [workspaceId, from, to]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    summary,
    loading,
    error,
    lastUpdatedAt,
    reload,
  };
}
