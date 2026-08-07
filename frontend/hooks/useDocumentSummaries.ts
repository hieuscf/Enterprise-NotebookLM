/**
 * =============================================================================
 * File: useDocumentSummaries.ts
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: Load Summary history + create/poll async generation (FR6 Part 3).
 * Responsibilities:
 *   - listDocumentSummaries on mount / reload
 *   - createDocumentSummary (POST 202) then poll getSummary until terminal
 *   - Single poll loop per processing summary id; stop on unmount
 * Dependencies:
 *   - lib/summaries.api, types/summaries
 * Public Exports:
 *   - useDocumentSummaries
 * Database/Table: N/A
 * Related Modules: features/summaries/SummarySection
 * Important Notes: Mirrors usePipelineStatus interval (~2.5s). Never POSTs on
 *   style switch — callers decide when to create.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  createDocumentSummary,
  getSummary,
  listDocumentSummaries,
} from "@/lib/summaries.api";
import { ApiClientError } from "@/lib/api-client";
import type { Summary, SummaryStyle } from "@/types/summaries";

const DEFAULT_INTERVAL_MS = 2500;

function isTerminal(status: Summary["status"]): boolean {
  return status === "completed" || status === "failed";
}

export function useDocumentSummaries(workspaceId: string, documentId: string) {
  const [summaries, setSummaries] = useState<Summary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const pollTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());
  const mountedRef = useRef(true);

  const stopPoll = useCallback((summaryId: string) => {
    const timer = pollTimers.current.get(summaryId);
    if (timer !== undefined) {
      clearInterval(timer);
      pollTimers.current.delete(summaryId);
    }
  }, []);

  const stopAllPolls = useCallback(() => {
    for (const id of [...pollTimers.current.keys()]) {
      stopPoll(id);
    }
  }, [stopPoll]);

  const upsertSummary = useCallback((row: Summary) => {
    setSummaries((prev) => {
      const without = prev.filter((s) => s.id !== row.id);
      return [row, ...without].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    });
  }, []);

  const pollOnce = useCallback(
    async (summaryId: string): Promise<boolean> => {
      try {
        const row = await getSummary(workspaceId, summaryId);
        if (!mountedRef.current) return true;
        upsertSummary(row);
        return isTerminal(row.status);
      } catch {
        return false;
      }
    },
    [upsertSummary, workspaceId],
  );

  const startPoll = useCallback(
    (summaryId: string) => {
      if (pollTimers.current.has(summaryId)) return;
      const timer = setInterval(() => {
        void pollOnce(summaryId).then((done) => {
          if (done) stopPoll(summaryId);
        });
      }, DEFAULT_INTERVAL_MS);
      pollTimers.current.set(summaryId, timer);
    },
    [pollOnce, stopPoll],
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listDocumentSummaries(workspaceId, documentId);
      if (!mountedRef.current) return;
      setSummaries(rows);
      for (const row of rows) {
        if (row.status === "processing") startPoll(row.id);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(
        err instanceof ApiClientError ? err.message : "Không tải được danh sách tóm tắt.",
      );
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [documentId, startPoll, workspaceId]);

  useEffect(() => {
    mountedRef.current = true;
    void reload();
    return () => {
      mountedRef.current = false;
      stopAllPolls();
    };
  }, [reload, stopAllPolls]);

  const createSummary = useCallback(
    async (style: SummaryStyle): Promise<Summary | null> => {
      if (creating) return null;
      setCreating(true);
      setError(null);
      try {
        const row = await createDocumentSummary(workspaceId, documentId, { style });
        if (!mountedRef.current) return row;
        upsertSummary(row);
        if (row.status === "processing") {
          startPoll(row.id);
          // Immediate follow-up fetch so UI updates faster than interval.
          void pollOnce(row.id).then((done) => {
            if (done) stopPoll(row.id);
          });
        }
        return row;
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof ApiClientError ? err.message : "Không tạo được tóm tắt.",
          );
        }
        return null;
      } finally {
        if (mountedRef.current) setCreating(false);
      }
    },
    [creating, documentId, pollOnce, startPoll, stopPoll, upsertSummary, workspaceId],
  );

  return {
    summaries,
    loading,
    error,
    creating,
    reload,
    createSummary,
  };
}
