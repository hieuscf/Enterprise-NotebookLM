/**
 * =============================================================================
 * File: useReportStatusPoll.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Poll GET /reports/{id} until status is ready or failed (UC8).
 * Responsibilities:
 *   - Poll every ~2s while reportId is set and status is pending
 *   - Stop on terminal status, unmount, or reportId clear
 * Dependencies:
 *   - lib/reports.api.getReport
 * Public Exports:
 *   - useReportStatusPoll
 * Database/Table: N/A
 * Related Modules: features/reports/ReportBuilder, hooks/useReports
 * Important Notes: Interval defaults to 2000ms per UC8 prompt.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getReport } from "@/lib/reports.api";
import type { Report } from "@/types/reports";

const DEFAULT_INTERVAL_MS = 2000;

function isTerminal(status: Report["status"]): boolean {
  return status === "ready" || status === "failed";
}

type Options = {
  intervalMs?: number;
  enabled?: boolean;
  onUpdate?: (report: Report) => void;
};

export function useReportStatusPoll(
  workspaceId: string,
  reportId: string | null,
  options: Options = {},
) {
  const { intervalMs = DEFAULT_INTERVAL_MS, enabled = true, onUpdate } = options;
  const [report, setReport] = useState<Report | null>(null);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;
  const mountedRef = useRef(true);

  const pollOnce = useCallback(async (): Promise<boolean> => {
    if (!reportId) return true;
    try {
      const row = await getReport(workspaceId, reportId);
      if (!mountedRef.current) return true;
      setReport(row);
      setError(null);
      onUpdateRef.current?.(row);
      return isTerminal(row.status);
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Không poll được báo cáo.");
      }
      return false;
    }
  }, [reportId, workspaceId]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled || !reportId) {
      setPolling(false);
      return;
    }

    let cancelled = false;
    setPolling(true);
    setReport(null);

    void pollOnce().then((done) => {
      if (cancelled || !mountedRef.current) return;
      if (done) setPolling(false);
    });

    const timer = setInterval(() => {
      void pollOnce().then((done) => {
        if (cancelled || !mountedRef.current) return;
        if (done) {
          clearInterval(timer);
          setPolling(false);
        }
      });
    }, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(timer);
      setPolling(false);
    };
  }, [enabled, intervalMs, pollOnce, reportId]);

  return { report, polling, error, refresh: pollOnce };
}
