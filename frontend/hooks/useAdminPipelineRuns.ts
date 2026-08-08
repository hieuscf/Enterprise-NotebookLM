/**
 * =============================================================================
 * File: useAdminPipelineRuns.ts
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Single shared fetch of recent pipeline_runs for both the Pipeline
 *          Health summary and the Recent Pipeline Activity table — avoids
 *          issuing two nearly-identical admin requests per dashboard load.
 * Responsibilities:
 *   - Fetch up to `pageSize` most-recent runs (no status filter), newest first
 *   - Expose loading/error/reload independent from other dashboard sections
 * Dependencies:
 *   - lib/admin.api.listWorkspacePipelineRuns
 * Public Exports:
 *   - useAdminPipelineRuns
 * Database/Table: pipeline_runs, pipeline_stage_logs
 * Related Modules: features/admin/PipelineHealthCard, RecentPipelineTable,
 *   features/admin/admin-format (derives status counts / stage rates)
 * Important Notes: The endpoint has no aggregate/count contract — status
 *   counts and stage completion below are derived from this bounded sample
 *   (see admin-format.ts), not a true whole-workspace total. Labelled as such
 *   in the UI (see PipelineHealthCard footnote).
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { listWorkspacePipelineRuns } from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import type { PipelineRun } from "@/types/documents";

const SAMPLE_PAGE_SIZE = 100;

export function useAdminPipelineRuns(workspaceId: string | null) {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkspacePipelineRuns(workspaceId, {
        page: 1,
        pageSize: SAMPLE_PAGE_SIZE,
      });
      setRuns(data);
    } catch (err) {
      setRuns([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được dữ liệu pipeline.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { runs, sampleCapped: runs.length >= SAMPLE_PAGE_SIZE, loading, error, reload };
}
