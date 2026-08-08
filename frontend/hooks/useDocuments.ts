/**
 * =============================================================================
 * File: useDocuments.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Client hook to load a workspace's paginated document list with an
 *          optional file_type filter (FR2 Part 2).
 * Responsibilities:
 *   - Fetch GET /workspaces/{id}/documents via BFF; expose loading/error/reload
 * Dependencies:
 *   - lib/api-client.listDocuments
 * Public Exports:
 *   - useDocuments
 * Database/Table: documents
 * Related Modules: features/documents/DocumentList, features/admin/AdminDashboardView
 * Important Notes: Refetches whenever page/pageSize/fileType change. Returns
 *   [] (not throwing) while workspaceId is empty/not-yet-resolved — same
 *   contract as useWorkspaceMembers, so callers picking a workspace async
 *   (e.g. the Admin Dashboard selector) don't fire a request with a blank id.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiClientError, listDocuments } from "@/lib/api-client";
import type { Document, FileType } from "@/types/documents";

export function useDocuments(
  workspaceId: string,
  params: { page: number; pageSize: number; fileType: FileType | null },
) {
  const { page, pageSize, fileType } = params;

  const [items, setItems] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listDocuments(workspaceId, { page, pageSize, fileType });
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setItems([]);
      setTotal(0);
      setError(
        err instanceof ApiClientError ? err.message : "Không tải được danh sách tài liệu.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId, page, pageSize, fileType]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { items, total, page, pageSize, loading, error, reload };
}
