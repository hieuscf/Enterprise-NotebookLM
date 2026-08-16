/**
 * =============================================================================
 * File: useReportPreview.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Load a single report for CMP-25 preview and poll while pending.
 * Responsibilities:
 *   - GET /workspaces/{id}/reports/{id} once; poll until ready|failed
 *   - Map HTTP errors to user-facing copy; retry via POST same sources
 *   - Download the backend-generated export (never generate in-browser)
 * Dependencies:
 *   - lib/reports.api, comparison-report-preview helpers
 * Public Exports:
 *   - useReportPreview
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview
 * Important Notes: Preview uses structured GET detail. Do not fetch export
 *   merely to render. Zero LLM calls.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { reportHttpMessage, retryPayload } from "@/features/reports/comparison-report-preview";
import { exportErrorMessage } from "@/features/reports/report-export";
import { ApiClientError } from "@/lib/api-client";
import { downloadBlob } from "@/lib/download";
import {
  createReport,
  downloadReportExport,
  getReport,
} from "@/lib/reports.api";
import type { Report } from "@/types/reports";

const POLL_INTERVAL_MS = 2000;

function isTerminal(status: Report["status"]): boolean {
  return status === "ready" || status === "failed";
}

export function useReportPreview(workspaceId: string, reportId: string) {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [exporting, setExporting] = useState(false);
  const mountedRef = useRef(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const applyError = useCallback((err: unknown, kind: "load" | "export" = "load") => {
    if (err instanceof ApiClientError) {
      setErrorStatus(err.status);
      setError(
        kind === "export"
          ? exportErrorMessage(err.status, err.code, err.message)
          : reportHttpMessage(err.status, err.message),
      );
      return;
    }
    setErrorStatus(null);
    setError(
      kind === "export" ? exportErrorMessage(0) : "Không tải được báo cáo.",
    );
  }, []);

  const load = useCallback(async (): Promise<Report | null> => {
    try {
      const row = await getReport(workspaceId, reportId);
      if (!mountedRef.current) return row;
      setReport(row);
      setError(null);
      setErrorStatus(null);
      return row;
    } catch (err) {
      if (mountedRef.current) applyError(err);
      return null;
    }
  }, [applyError, reportId, workspaceId]);

  useEffect(() => {
    mountedRef.current = true;
    setLoading(true);
    void load().finally(() => {
      if (mountedRef.current) setLoading(false);
    });
    return () => {
      mountedRef.current = false;
      stopPoll();
    };
  }, [load, stopPoll]);

  useEffect(() => {
    stopPoll();
    if (!report || isTerminal(report.status)) return;
    pollRef.current = setInterval(() => {
      void load().then((row) => {
        if (row && isTerminal(row.status)) stopPoll();
      });
    }, POLL_INTERVAL_MS);
    return stopPoll;
  }, [load, report, stopPoll]);

  const retry = useCallback(async (): Promise<Report | null> => {
    if (!report || retrying) return null;
    const body = retryPayload(report);
    if (!body) {
      setError("Không đủ thông tin nguồn để tạo lại báo cáo.");
      return null;
    }
    setRetrying(true);
    setError(null);
    try {
      const created = await createReport(workspaceId, body);
      if (!mountedRef.current) return created;
      return created;
    } catch (err) {
      if (mountedRef.current) applyError(err);
      return null;
    } finally {
      if (mountedRef.current) setRetrying(false);
    }
  }, [applyError, report, retrying, workspaceId]);

  const exportReport = useCallback(async (): Promise<boolean> => {
    if (!report || report.status !== "ready" || exporting) return false;
    setExporting(true);
    setError(null);
    try {
      const file = await downloadReportExport(workspaceId, report.id);
      downloadBlob(file.blob, file.filename);
      return true;
    } catch (err) {
      if (mountedRef.current) applyError(err, "export");
      return false;
    } finally {
      if (mountedRef.current) setExporting(false);
    }
  }, [applyError, exporting, report, workspaceId]);

  return {
    report,
    loading,
    error,
    errorStatus,
    retrying,
    exporting,
    reload: load,
    retry,
    exportReport,
  };
}
