/**
 * =============================================================================
 * File: usePipelineStatus.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Poll GET .../versions/{versionId}/pipeline-status until terminal
 *          state, for the "realtime" 6-stage tracker (FR2 / FR13).
 * Responsibilities:
 *   - setInterval-based polling (default 2.5s), stop on completed/failed
 *   - Surface connection loss distinctly from "still running" so the UI can
 *     show a manual retry affordance instead of spinning forever
 * Dependencies:
 *   - lib/api-client.getPipelineStatus
 * Public Exports:
 *   - usePipelineStatus
 * Database/Table: pipeline_runs, pipeline_stage_logs
 * Related Modules: features/documents/PipelineStatusTracker
 * Important Notes: No WebSocket/SSE in the current API contract — polling is
 *   the intended "realtime" mechanism per Enterprise_notebooklm_openapi.yaml.
 *   Do not switch this to a socket without confirming a backend change first.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getPipelineStatus } from "@/lib/api-client";
import { isTerminalPipelineStatus } from "@/lib/pipeline-stages";
import type { PipelineRun } from "@/types/documents";

const DEFAULT_INTERVAL_MS = 2500;

function isRunTerminal(run: PipelineRun): boolean {
  if (isTerminalPipelineStatus(run.status)) return true;
  return run.stages.some((stage) => stage.status === "failed");
}

export function usePipelineStatus(
  workspaceId: string,
  documentId: string,
  versionId: string,
  options?: { intervalMs?: number },
) {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;

  const [run, setRun] = useState<PipelineRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionLost, setConnectionLost] = useState(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const fetchOnce = useCallback(async (): Promise<boolean> => {
    try {
      const data = await getPipelineStatus(workspaceId, documentId, versionId);
      setRun(data);
      setConnectionLost(false);
      return isRunTerminal(data);
    } catch {
      setConnectionLost(true);
      return true; // treat as "stop auto-polling" — caller must retry manually
    } finally {
      setLoading(false);
    }
  }, [workspaceId, documentId, versionId]);

  const startPolling = useCallback(() => {
    clearTimer();
    timerRef.current = setInterval(() => {
      void fetchOnce().then((shouldStop) => {
        if (shouldStop) clearTimer();
      });
    }, intervalMs);
  }, [clearTimer, fetchOnce, intervalMs]);

  useEffect(() => {
    setLoading(true);
    setConnectionLost(false);
    void fetchOnce().then((shouldStop) => {
      if (!shouldStop) startPolling();
    });
    return clearTimer;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, documentId, versionId]);

  const retry = useCallback(() => {
    void fetchOnce().then((shouldStop) => {
      if (!shouldStop) startPolling();
    });
  }, [fetchOnce, startPolling]);

  return { run, loading, connectionLost, retry };
}
