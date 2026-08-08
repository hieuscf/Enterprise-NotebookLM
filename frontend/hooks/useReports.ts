/**
 * =============================================================================
 * File: useReports.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Load Report list + create/delete/download; wire status polling (FR9).
 * Responsibilities:
 *   - listReports on mount / reload
 *   - createReport (POST 202) then rely on useReportStatusPoll / list upsert
 *   - deleteReport; downloadReportExport via Blob
 * Dependencies:
 *   - lib/reports.api, hooks/useReportStatusPoll, lib/download
 * Public Exports:
 *   - useReports
 * Database/Table: N/A
 * Related Modules: features/reports/*
 * Important Notes: Polling for active create is owned by ReportBuilder via
 *   useReportStatusPoll; this hook also polls pending rows found on reload.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiClientError } from "@/lib/api-client";
import { downloadBlob } from "@/lib/download";
import {
  createReport,
  deleteReport,
  downloadReportExport,
  getReport,
  listReports,
} from "@/lib/reports.api";
import type { Report, ReportCreateRequest } from "@/types/reports";

const LIST_POLL_INTERVAL_MS = 2000;

function isTerminal(status: Report["status"]): boolean {
  return status === "ready" || status === "failed";
}

export function useReports(workspaceId: string) {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const pollTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(
    new Map(),
  );
  const mountedRef = useRef(true);

  const stopPoll = useCallback((reportId: string) => {
    const timer = pollTimers.current.get(reportId);
    if (timer !== undefined) {
      clearInterval(timer);
      pollTimers.current.delete(reportId);
    }
  }, []);

  const stopAllPolls = useCallback(() => {
    for (const id of [...pollTimers.current.keys()]) {
      stopPoll(id);
    }
  }, [stopPoll]);

  const upsertReport = useCallback((row: Report) => {
    setReports((prev) => {
      const without = prev.filter((r) => r.id !== row.id);
      return [row, ...without].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    });
  }, []);

  const pollOnce = useCallback(
    async (reportId: string): Promise<boolean> => {
      try {
        const row = await getReport(workspaceId, reportId);
        if (!mountedRef.current) return true;
        upsertReport(row);
        return isTerminal(row.status);
      } catch {
        return false;
      }
    },
    [upsertReport, workspaceId],
  );

  const startPoll = useCallback(
    (reportId: string) => {
      if (pollTimers.current.has(reportId)) return;
      const timer = setInterval(() => {
        void pollOnce(reportId).then((done) => {
          if (done) stopPoll(reportId);
        });
      }, LIST_POLL_INTERVAL_MS);
      pollTimers.current.set(reportId, timer);
    },
    [pollOnce, stopPoll],
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listReports(workspaceId, { page: 1, pageSize: 50 });
      if (!mountedRef.current) return;
      setReports(rows);
      for (const row of rows) {
        if (row.status === "pending") startPoll(row.id);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được danh sách báo cáo.",
      );
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [startPoll, workspaceId]);

  useEffect(() => {
    mountedRef.current = true;
    void reload();
    return () => {
      mountedRef.current = false;
      stopAllPolls();
    };
  }, [reload, stopAllPolls]);

  const create = useCallback(
    async (body: ReportCreateRequest): Promise<Report | null> => {
      if (creating) return null;
      if (!body.items.length) {
        setError("Chọn ít nhất một nguồn cho báo cáo.");
        return null;
      }
      setCreating(true);
      setError(null);
      try {
        const row = await createReport(workspaceId, body);
        if (!mountedRef.current) return row;
        upsertReport(row);
        if (row.status === "pending") {
          startPoll(row.id);
          void pollOnce(row.id).then((done) => {
            if (done) stopPoll(row.id);
          });
        }
        return row;
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof ApiClientError
              ? err.message
              : "Không tạo được báo cáo.",
          );
        }
        return null;
      } finally {
        if (mountedRef.current) setCreating(false);
      }
    },
    [creating, pollOnce, startPoll, stopPoll, upsertReport, workspaceId],
  );

  const remove = useCallback(
    async (reportId: string): Promise<boolean> => {
      if (deletingId) return false;
      setDeletingId(reportId);
      setError(null);
      try {
        await deleteReport(workspaceId, reportId);
        if (!mountedRef.current) return true;
        stopPoll(reportId);
        setReports((prev) => prev.filter((r) => r.id !== reportId));
        return true;
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof ApiClientError
              ? err.message
              : "Không xoá được báo cáo.",
          );
        }
        return false;
      } finally {
        if (mountedRef.current) setDeletingId(null);
      }
    },
    [deletingId, stopPoll, workspaceId],
  );

  const download = useCallback(
    async (reportId: string): Promise<boolean> => {
      if (downloadingId) return false;
      setDownloadingId(reportId);
      setError(null);
      try {
        const file = await downloadReportExport(workspaceId, reportId);
        downloadBlob(file.blob, file.filename);
        return true;
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof ApiClientError
              ? err.message
              : "Không tải được file báo cáo.",
          );
        }
        return false;
      } finally {
        if (mountedRef.current) setDownloadingId(null);
      }
    },
    [downloadingId, workspaceId],
  );

  return {
    reports,
    loading,
    error,
    creating,
    deletingId,
    downloadingId,
    reload,
    create,
    remove,
    download,
    upsertReport,
    clearError: () => setError(null),
  };
}
