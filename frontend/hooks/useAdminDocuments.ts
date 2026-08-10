/**
 * =============================================================================
 * File: useAdminDocuments.ts
 * Module/Service: Admin Document Management (Web App) — FR2 / FR12
 * Layer: UI
 * Purpose: Server-paginated fetch for GET /admin/documents with Manage gate.
 * Responsibilities:
 *   - Load list + summary when caller is platform Manage
 *   - Expose reload for Refresh / filter changes
 * Dependencies:
 *   - hooks/useAuth, lib/admin.api, lib/rbac, types/admin
 * Public Exports:
 *   - useAdminDocuments
 * Database/Table: documents, document_versions (via Admin API)
 * Related Modules: features/admin/AdminDocumentsView
 * Important Notes: Does not fetch all enterprise documents client-side.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/hooks/useAuth";
import { listAdminDocuments } from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import { canAccessAdmin } from "@/lib/rbac";
import type {
  AdminDocumentListItem,
  AdminDocumentListParams,
  AdminDocumentSummary,
} from "@/types/admin";

const EMPTY_SUMMARY: AdminDocumentSummary = {
  total: 0,
  processing: 0,
  ready: 0,
  failed: 0,
};

export function useAdminDocuments(params: AdminDocumentListParams) {
  const { user, loading: authLoading } = useAuth();
  const isManage = canAccessAdmin(user);

  const [items, setItems] = useState<AdminDocumentListItem[]>([]);
  const [summary, setSummary] = useState<AdminDocumentSummary>(EMPTY_SUMMARY);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(params.page ?? 1);
  const [pageSize, setPageSize] = useState(params.pageSize ?? 20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (authLoading) return;
    if (!isManage) {
      setItems([]);
      setSummary(EMPTY_SUMMARY);
      setTotal(0);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await listAdminDocuments(params);
      setItems(data.items);
      setSummary(data.summary);
      setTotal(data.total);
      setPage(data.page);
      setPageSize(data.page_size);
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.status === 403) {
          setError("You don't have permission to view enterprise documents.");
        } else if (err.status === 401) {
          setError("Your session has expired. Please sign in again.");
        } else {
          setError("Unable to load documents. Something went wrong while retrieving enterprise documents.");
        }
      } else {
        setError("Unable to load documents. Something went wrong while retrieving enterprise documents.");
      }
      setItems([]);
      setSummary(EMPTY_SUMMARY);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [
    authLoading,
    isManage,
    params.page,
    params.pageSize,
    params.workspaceId,
    params.status,
    params.fileType,
    params.search,
    params.sort,
    params.order,
  ]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    items,
    summary,
    total,
    page,
    pageSize,
    loading: authLoading || loading,
    error,
    reload,
    isManage,
  };
}
