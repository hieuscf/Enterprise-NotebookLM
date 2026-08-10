/**
 * =============================================================================
 * File: useAdminPipelineConsole.ts
 * Module/Service: Observability Module (Web App) — FR13
 * Layer: UI
 * Purpose: Data hook for `/admin/pipeline` — paginated runs + overview sample.
 * Responsibilities:
 *   - Fetch table page with server-side status filter + pagination
 *   - Fetch bounded overview sample (no status filter) for KPI cards
 *   - Optional UI auto-refresh interval (no websocket)
 * Dependencies:
 *   - lib/admin.api.listWorkspacePipelineRuns
 * Public Exports:
 *   - useAdminPipelineConsole
 * Database/Table: pipeline_runs, pipeline_stage_logs
 * Related Modules: features/admin/AdminPipelineView
 * Important Notes: Overview counts are sample-derived — no aggregate endpoint.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { listWorkspacePipelineRuns } from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import type { PipelineRun, PipelineStatus } from "@/types/documents";

const OVERVIEW_SAMPLE_SIZE = 100;

export type AdminPipelineConsoleParams = {
  workspaceId: string | null;
  status: PipelineStatus | null;
  page: number;
  pageSize: number;
  autoRefreshMs?: number | null;
};

export function useAdminPipelineConsole({
  workspaceId,
  status,
  page,
  pageSize,
  autoRefreshMs = 10_000,
}: AdminPipelineConsoleParams) {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [overviewRuns, setOverviewRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const requestId = useRef(0);

  const reload = useCallback(async () => {
    if (!workspaceId) {
      setRuns([]);
      setOverviewRuns([]);
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
      const [pageRuns, sample] = await Promise.all([
        listWorkspacePipelineRuns(workspaceId, {
          status,
          page,
          pageSize,
        }),
        listWorkspacePipelineRuns(workspaceId, {
          status: null,
          page: 1,
          pageSize: OVERVIEW_SAMPLE_SIZE,
        }),
      ]);
      if (id !== requestId.current) return;
      setRuns(pageRuns);
      setOverviewRuns(sample);
      setLastUpdatedAt(Date.now());
    } catch (err) {
      if (id !== requestId.current) return;
      setRuns([]);
      setOverviewRuns([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load pipeline runs.",
      );
    } finally {
      if (id === requestId.current) {
        setLoading(false);
        setOverviewLoading(false);
      }
    }
  }, [workspaceId, status, page, pageSize]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!workspaceId || !autoRefreshMs || autoRefreshMs <= 0) return;
    const timer = window.setInterval(() => {
      void reload();
    }, autoRefreshMs);
    return () => window.clearInterval(timer);
  }, [workspaceId, autoRefreshMs, reload]);

  return {
    runs,
    overviewRuns,
    overviewSampleCapped: overviewRuns.length >= OVERVIEW_SAMPLE_SIZE,
    loading,
    overviewLoading,
    error,
    lastUpdatedAt,
    reload,
    hasNextPage: runs.length >= pageSize,
  };
}
