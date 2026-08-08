/**
 * =============================================================================
 * File: useReportSources.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Load selectable report sources across summary/extraction/comparison/chat.
 * Responsibilities:
 *   - Aggregate completed summaries & extractions from workspace documents
 *   - List completed comparisons + chat sessions for picker tabs
 * Dependencies:
 *   - listDocuments, summaries.api, extractions.api, comparisons.api, chat.api
 * Public Exports:
 *   - useReportSources, ReportSourceOption
 * Database/Table: N/A
 * Related Modules: features/reports/ReportBuilder
 * Important Notes: Summaries/extractions are document-scoped APIs — FE flattens.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { styleLabel } from "@/features/summaries/summary-format";
import { EXTRACTION_TYPE_OPTIONS } from "@/features/extractions/extraction-format";
import { ApiClientError, listDocuments } from "@/lib/api-client";
import { listChatSessions } from "@/lib/chat.api";
import { listComparisons } from "@/lib/comparisons.api";
import { listDocumentExtractions } from "@/lib/extractions.api";
import { listDocumentSummaries } from "@/lib/summaries.api";
import type { ReportSourceType } from "@/types/reports";

export type ReportSourceOption = {
  source_type: ReportSourceType;
  source_id: string;
  label: string;
  meta?: string;
};

function extractionTypeLabel(type: string): string {
  return (
    EXTRACTION_TYPE_OPTIONS.find((o) => o.type === type)?.label ?? type
  );
}

export function useReportSources(workspaceId: string) {
  const [summaries, setSummaries] = useState<ReportSourceOption[]>([]);
  const [extractions, setExtractions] = useState<ReportSourceOption[]>([]);
  const [comparisons, setComparisons] = useState<ReportSourceOption[]>([]);
  const [chatSessions, setChatSessions] = useState<ReportSourceOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [docsPage, comparisonRows, sessions] = await Promise.all([
        listDocuments(workspaceId, { page: 1, pageSize: 50 }),
        listComparisons(workspaceId, { page: 1, pageSize: 50 }),
        listChatSessions(workspaceId),
      ]);

      const docs = docsPage.items ?? [];
      const titleByDoc = new Map(docs.map((d) => [d.id, d.title]));

      const summaryBuckets = await Promise.all(
        docs.map(async (doc) => {
          try {
            const rows = await listDocumentSummaries(workspaceId, doc.id);
            return rows
              .filter((s) => s.status === "completed")
              .map(
                (s): ReportSourceOption => ({
                  source_type: "summary",
                  source_id: s.id,
                  label: `${styleLabel(s.style)} — ${doc.title}`,
                  meta: s.created_at,
                }),
              );
          } catch {
            return [] as ReportSourceOption[];
          }
        }),
      );

      const extractionBuckets = await Promise.all(
        docs.map(async (doc) => {
          try {
            const rows = await listDocumentExtractions(workspaceId, doc.id);
            return rows
              .filter((e) => e.status === "completed")
              .map(
                (e): ReportSourceOption => ({
                  source_type: "extraction",
                  source_id: e.id,
                  label: `${extractionTypeLabel(e.extraction_type)} — ${doc.title}`,
                  meta: e.created_at,
                }),
              );
          } catch {
            return [] as ReportSourceOption[];
          }
        }),
      );

      setSummaries(summaryBuckets.flat());
      setExtractions(extractionBuckets.flat());
      setComparisons(
        comparisonRows
          .filter((c) => c.status === "completed")
          .map((c) => {
            const titles = c.document_ids
              .map((id) => titleByDoc.get(id) ?? id.slice(0, 8))
              .slice(0, 3)
              .join(" · ");
            return {
              source_type: "comparison" as const,
              source_id: c.id,
              label: titles || `So sánh ${c.id.slice(0, 8)}`,
              meta: c.created_at,
            };
          }),
      );
      setChatSessions(
        sessions.map((s) => ({
          source_type: "chat_session" as const,
          source_id: s.id,
          label: (s.title || "").trim() || `Phiên chat ${s.id.slice(0, 8)}`,
          meta: s.updated_at,
        })),
      );
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được danh sách nguồn báo cáo.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    summaries,
    extractions,
    comparisons,
    chatSessions,
    loading,
    error,
    reload,
  };
}
