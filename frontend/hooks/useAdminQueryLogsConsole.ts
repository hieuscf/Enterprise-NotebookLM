/**
 * =============================================================================
 * File: useAdminQueryLogsConsole.ts
 * Module/Service: Observability Module (Web App) — FR13
 * Layer: UI
 * Purpose: Data hook for `/admin/query-logs` — paginated logs + overview sample.
 * Responsibilities:
 *   - Fetch table page with server-side route_type filter + pagination
 *   - Fetch bounded overview sample (no route filter) for KPI / distribution
 *   - Manual reload only (no websocket / fake realtime)
 * Dependencies:
 *   - lib/admin.api.listWorkspaceQueryLogs
 * Public Exports:
 *   - useAdminQueryLogsConsole
 * Database/Table: query_logs
 * Related Modules: features/admin/AdminQueryLogsView
 * Important Notes: Overview counts are sample-derived — API returns QueryLog[]
 *   without total/aggregate metadata. Do not invent pagination totals.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { listWorkspaceQueryLogs } from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import type { QueryLogItem } from "@/types/admin";
import type { RouteType } from "@/types/chat";

const OVERVIEW_SAMPLE_SIZE = 100;

export type AdminQueryLogsConsoleParams = {
  workspaceId: string | null;
  routeType: RouteType | null;
  page: number;
  pageSize: number;
};

export function useAdminQueryLogsConsole({
  workspaceId,
  routeType,
  page,
  pageSize,
}: AdminQueryLogsConsoleParams) {
  const [logs, setLogs] = useState<QueryLogItem[]>([]);
  const [overviewLogs, setOverviewLogs] = useState<QueryLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const requestId = useRef(0);

  const reload = useCallback(async () => {
    if (!workspaceId) {
      setLogs([]);
      setOverviewLogs([]);
      setLoading(false);
      setOverviewLoading(false);
      setError(null);
      return;
    }

    const id = ++requestId.current;
    setLoading(true);
    setOverviewLoading(true);
    setError(null);

    try {
      const [pageLogs, sample] = await Promise.all([
        listWorkspaceQueryLogs(workspaceId, {
          routeType,
          page,
          pageSize,
        }),
        listWorkspaceQueryLogs(workspaceId, {
          routeType: null,
          page: 1,
          pageSize: OVERVIEW_SAMPLE_SIZE,
        }),
      ]);
      if (id !== requestId.current) return;
      setLogs(pageLogs);
      setOverviewLogs(sample);
      setLastUpdatedAt(Date.now());
    } catch (err) {
      if (id !== requestId.current) return;
      setLogs([]);
      setOverviewLogs([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load query logs.",
      );
    } finally {
      if (id === requestId.current) {
        setLoading(false);
        setOverviewLoading(false);
      }
    }
  }, [workspaceId, routeType, page, pageSize]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    logs,
    overviewLogs,
    overviewSampleCapped: overviewLogs.length >= OVERVIEW_SAMPLE_SIZE,
    loading,
    overviewLoading,
    error,
    lastUpdatedAt,
    reload,
    hasNextPage: logs.length >= pageSize,
  };
}
