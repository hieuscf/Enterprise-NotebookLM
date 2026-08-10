/**
 * =============================================================================
 * File: admin.api.ts
 * Module/Service: Observability / Admin Console (Web App)
 * Layer: UI
 * Purpose: Typed calls to Admin contract — observability + global documents.
 * Responsibilities:
 *   - listWorkspaceQueryLogs / listWorkspacePipelineRuns / getWorkspaceCostSummary
 *   - listAdminDocuments / getAdminDocument / listAdminDocumentVersions
 * Dependencies:
 *   - lib/api-client (apiFetch, parseApiError, apiJson)
 * Public Exports:
 *   - listWorkspaceQueryLogs, listWorkspacePipelineRuns, getWorkspaceCostSummary
 *   - listAdminDocuments, getAdminDocument, listAdminDocumentVersions
 * Database/Table: query_logs, pipeline_runs, documents, document_versions
 * Related Modules: hooks/useAdmin*, features/admin/*
 * Important Notes:
 *   - Platform Manage only — backend require_platform_manage is authoritative.
 * =============================================================================
 */

import { apiFetch, parseApiError } from "@/lib/api-client";
import type {
  AdminDocumentDetail,
  AdminDocumentListParams,
  AdminDocumentListResponse,
  CostSummary,
  QueryLogItem,
} from "@/types/admin";
import type { RouteType } from "@/types/chat";
import type { DocumentVersion, PipelineRun, PipelineStatus } from "@/types/documents";

export async function listWorkspaceQueryLogs(
  workspaceId: string,
  params?: { routeType?: RouteType | null; page?: number; pageSize?: number },
): Promise<QueryLogItem[]> {
  const qs = new URLSearchParams({
    page: String(params?.page ?? 1),
    page_size: String(params?.pageSize ?? 20),
  });
  if (params?.routeType) qs.set("route_type", params.routeType);
  const response = await apiFetch(
    `/admin/workspaces/${workspaceId}/query-logs?${qs.toString()}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as QueryLogItem[];
}

export async function listWorkspacePipelineRuns(
  workspaceId: string,
  params?: { status?: PipelineStatus | null; page?: number; pageSize?: number },
): Promise<PipelineRun[]> {
  const qs = new URLSearchParams({
    page: String(params?.page ?? 1),
    page_size: String(params?.pageSize ?? 20),
  });
  if (params?.status) qs.set("status", params.status);
  const response = await apiFetch(
    `/admin/workspaces/${workspaceId}/pipeline-runs?${qs.toString()}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as PipelineRun[];
}

export async function getWorkspaceCostSummary(
  workspaceId: string,
  params?: { from?: string | null; to?: string | null },
): Promise<CostSummary> {
  const qs = new URLSearchParams();
  if (params?.from) qs.set("from", params.from);
  if (params?.to) qs.set("to", params.to);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const response = await apiFetch(
    `/admin/workspaces/${workspaceId}/cost-summary${suffix}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as CostSummary;
}

// ---------------------------------------------------------------------------
// Admin Documents — global document operations (Manage)
// ---------------------------------------------------------------------------

export async function listAdminDocuments(
  params?: AdminDocumentListParams,
): Promise<AdminDocumentListResponse> {
  const qs = new URLSearchParams({
    page: String(params?.page ?? 1),
    page_size: String(params?.pageSize ?? 20),
    sort: params?.sort ?? "updated_at",
    order: params?.order ?? "desc",
  });
  if (params?.workspaceId) qs.set("workspace_id", params.workspaceId);
  if (params?.status) qs.set("status", params.status);
  if (params?.fileType) qs.set("file_type", params.fileType);
  if (params?.search?.trim()) qs.set("search", params.search.trim());
  const response = await apiFetch(`/admin/documents?${qs.toString()}`);
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as AdminDocumentListResponse;
}

export async function getAdminDocument(
  documentId: string,
): Promise<AdminDocumentDetail> {
  const response = await apiFetch(`/admin/documents/${documentId}`);
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as AdminDocumentDetail;
}

export async function listAdminDocumentVersions(
  documentId: string,
): Promise<DocumentVersion[]> {
  const response = await apiFetch(`/admin/documents/${documentId}/versions`);
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as DocumentVersion[];
}
