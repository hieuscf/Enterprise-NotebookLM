/**
 * =============================================================================
 * File: useDocumentExtractions.ts
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Load Extraction history + create/poll async generation (FR7 Part 6).
 * Responsibilities:
 *   - listDocumentExtractions on mount / reload
 *   - createDocumentExtraction (POST 202) then poll getExtraction until terminal
 *   - Single poll loop per processing extraction id; stop on unmount
 * Dependencies:
 *   - lib/extractions.api, types/extractions
 * Public Exports:
 *   - useDocumentExtractions
 * Database/Table: N/A
 * Related Modules: features/extractions/ExtractionSection
 * Important Notes: Mirrors useDocumentSummaries (~2.5s). Never POSTs on
 *   type/format switch — callers decide when to create.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  createDocumentExtraction,
  getExtraction,
  listDocumentExtractions,
} from "@/lib/extractions.api";
import { ApiClientError } from "@/lib/api-client";
import type {
  Extraction,
  ExtractionOutputFormat,
  ExtractionType,
} from "@/types/extractions";

const DEFAULT_INTERVAL_MS = 2500;

function isTerminal(status: Extraction["status"]): boolean {
  return status === "completed" || status === "failed";
}

export function useDocumentExtractions(workspaceId: string, documentId: string) {
  const [extractions, setExtractions] = useState<Extraction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const pollTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());
  const mountedRef = useRef(true);

  const stopPoll = useCallback((extractionId: string) => {
    const timer = pollTimers.current.get(extractionId);
    if (timer !== undefined) {
      clearInterval(timer);
      pollTimers.current.delete(extractionId);
    }
  }, []);

  const stopAllPolls = useCallback(() => {
    for (const id of [...pollTimers.current.keys()]) {
      stopPoll(id);
    }
  }, [stopPoll]);

  const upsertExtraction = useCallback((row: Extraction) => {
    setExtractions((prev) => {
      const without = prev.filter((e) => e.id !== row.id);
      return [row, ...without].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    });
  }, []);

  const pollOnce = useCallback(
    async (extractionId: string): Promise<boolean> => {
      try {
        const row = await getExtraction(workspaceId, extractionId);
        if (!mountedRef.current) return true;
        upsertExtraction(row);
        return isTerminal(row.status);
      } catch {
        return false;
      }
    },
    [upsertExtraction, workspaceId],
  );

  const startPoll = useCallback(
    (extractionId: string) => {
      if (pollTimers.current.has(extractionId)) return;
      const timer = setInterval(() => {
        void pollOnce(extractionId).then((done) => {
          if (done) stopPoll(extractionId);
        });
      }, DEFAULT_INTERVAL_MS);
      pollTimers.current.set(extractionId, timer);
    },
    [pollOnce, stopPoll],
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listDocumentExtractions(workspaceId, documentId);
      if (!mountedRef.current) return;
      setExtractions(rows);
      for (const row of rows) {
        if (row.status === "processing") startPoll(row.id);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được danh sách trích xuất.",
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

  const createExtraction = useCallback(
    async (
      extractionType: ExtractionType,
      outputFormat: ExtractionOutputFormat,
    ): Promise<Extraction | null> => {
      if (creating) return null;
      setCreating(true);
      setError(null);
      try {
        const row = await createDocumentExtraction(workspaceId, documentId, {
          extraction_type: extractionType,
          output_format: outputFormat,
        });
        if (!mountedRef.current) return row;
        upsertExtraction(row);
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
              : "Không tạo được trích xuất.",
          );
        }
        return null;
      } finally {
        if (mountedRef.current) setCreating(false);
      }
    },
    [
      creating,
      documentId,
      pollOnce,
      startPoll,
      stopPoll,
      upsertExtraction,
      workspaceId,
    ],
  );

  return {
    extractions,
    loading,
    error,
    creating,
    reload,
    createExtraction,
  };
}
