/**
 * =============================================================================
 * File: useComparisons.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Load Comparison history + create/poll/delete async generation (FR8).
 * Responsibilities:
 *   - listComparisons on mount / reload
 *   - createComparison (POST 202) then poll getComparison until terminal
 *   - deleteComparison; single poll loop per processing id
 * Dependencies:
 *   - lib/comparisons.api, types/comparisons
 * Public Exports:
 *   - useComparisons
 * Database/Table: N/A
 * Related Modules: features/comparisons/ComparisonsView
 * Important Notes: Mirrors useDocumentExtractions (~2.5s poll interval).
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiClientError } from "@/lib/api-client";
import {
  createComparison,
  deleteComparison,
  getComparison,
  listComparisons,
} from "@/lib/comparisons.api";
import type { Comparison } from "@/types/comparisons";

const DEFAULT_INTERVAL_MS = 2500;

function isTerminal(status: Comparison["status"]): boolean {
  return status === "completed" || status === "failed";
}

export function useComparisons(workspaceId: string) {
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const pollTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(
    new Map(),
  );
  const mountedRef = useRef(true);

  const stopPoll = useCallback((comparisonId: string) => {
    const timer = pollTimers.current.get(comparisonId);
    if (timer !== undefined) {
      clearInterval(timer);
      pollTimers.current.delete(comparisonId);
    }
  }, []);

  const stopAllPolls = useCallback(() => {
    for (const id of [...pollTimers.current.keys()]) {
      stopPoll(id);
    }
  }, [stopPoll]);

  const upsertComparison = useCallback((row: Comparison) => {
    setComparisons((prev) => {
      const without = prev.filter((c) => c.id !== row.id);
      return [row, ...without].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    });
  }, []);

  const pollOnce = useCallback(
    async (comparisonId: string): Promise<boolean> => {
      try {
        const row = await getComparison(workspaceId, comparisonId);
        if (!mountedRef.current) return true;
        upsertComparison(row);
        return isTerminal(row.status);
      } catch {
        return false;
      }
    },
    [upsertComparison, workspaceId],
  );

  const startPoll = useCallback(
    (comparisonId: string) => {
      if (pollTimers.current.has(comparisonId)) return;
      const timer = setInterval(() => {
        void pollOnce(comparisonId).then((done) => {
          if (done) stopPoll(comparisonId);
        });
      }, DEFAULT_INTERVAL_MS);
      pollTimers.current.set(comparisonId, timer);
    },
    [pollOnce, stopPoll],
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listComparisons(workspaceId, {
        page: 1,
        pageSize: 50,
      });
      if (!mountedRef.current) return;
      setComparisons(rows);
      for (const row of rows) {
        if (row.status === "processing") startPoll(row.id);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được danh sách so sánh.",
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
    async (
      documentIds: string[],
      focus?: string | null,
    ): Promise<Comparison | null> => {
      if (creating) return null;
      if (documentIds.length < 2) {
        setError("Chọn ít nhất 2 tài liệu để so sánh.");
        return null;
      }
      setCreating(true);
      setError(null);
      try {
        const row = await createComparison(workspaceId, {
          document_ids: documentIds,
          focus,
        });
        if (!mountedRef.current) return row;
        upsertComparison(row);
        if (row.status === "processing") {
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
              : "Không tạo được so sánh.",
          );
        }
        return null;
      } finally {
        if (mountedRef.current) setCreating(false);
      }
    },
    [creating, pollOnce, startPoll, stopPoll, upsertComparison, workspaceId],
  );

  const remove = useCallback(
    async (comparisonId: string): Promise<boolean> => {
      if (deletingId) return false;
      setDeletingId(comparisonId);
      setError(null);
      try {
        await deleteComparison(workspaceId, comparisonId);
        if (!mountedRef.current) return true;
        stopPoll(comparisonId);
        setComparisons((prev) => prev.filter((c) => c.id !== comparisonId));
        return true;
      } catch (err) {
        if (mountedRef.current) {
          setError(
            err instanceof ApiClientError
              ? err.message
              : "Không xoá được so sánh.",
          );
        }
        return false;
      } finally {
        if (mountedRef.current) setDeletingId(null);
      }
    },
    [deletingId, stopPoll, workspaceId],
  );

  return {
    comparisons,
    loading,
    error,
    creating,
    deletingId,
    reload,
    create,
    remove,
    clearError: () => setError(null),
  };
}
