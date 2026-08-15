/**
 * =============================================================================
 * File: comparisons.api.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Typed calls to /workspaces/{id}/comparisons (FR8).
 * Responsibilities:
 *   - list / create / get / delete / review Comparisons
 * Dependencies:
 *   - lib/api-client (apiFetch, parseApiError)
 * Public Exports:
 *   listComparisons, createComparison, getComparison, deleteComparison,
 *   updateComparisonReview, createComparisonComment, updateComparisonComment,
 *   deleteComparisonComment
 * Database/Table: N/A
 * Related Modules: hooks/useComparisons, features/comparisons/*
 * Important Notes: POST returns 202 with status=processing — FE must poll.
 * =============================================================================
 */

import { apiFetch, parseApiError } from "@/lib/api-client";
import type {
  Comparison,
  ComparisonAuditTrail,
  ComparisonCommentTarget,
  ComparisonCreateRequest,
} from "@/types/comparisons";

export async function listComparisons(
  workspaceId: string,
  params?: { page?: number; pageSize?: number },
): Promise<Comparison[]> {
  const page = params?.page ?? 1;
  const pageSize = params?.pageSize ?? 20;
  const qs = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons?${qs.toString()}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Comparison[];
}

export async function createComparison(
  workspaceId: string,
  body: ComparisonCreateRequest,
): Promise<Comparison> {
  const response = await apiFetch(`/workspaces/${workspaceId}/comparisons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_ids: body.document_ids,
      ...(body.focus != null && body.focus.trim()
        ? { focus: body.focus.trim() }
        : {}),
    }),
  });
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Comparison;
}

export async function getComparison(
  workspaceId: string,
  comparisonId: string,
): Promise<Comparison> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons/${comparisonId}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Comparison;
}

export async function updateComparisonReview(
  workspaceId: string,
  comparisonId: string,
  body: { clause_id: string; status: string },
): Promise<Comparison> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons/${comparisonId}/review`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clause_id: body.clause_id,
        status: body.status,
      }),
    },
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Comparison;
}

export async function createComparisonComment(
  workspaceId: string,
  comparisonId: string,
  body: {
    clause_id: string;
    body: string;
    target_type?: ComparisonCommentTarget;
    target_id?: string | null;
  },
): Promise<Comparison> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons/${comparisonId}/comments`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clause_id: body.clause_id,
        body: body.body,
        target_type: body.target_type ?? "CLAUSE",
        ...(body.target_id ? { target_id: body.target_id } : {}),
      }),
    },
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Comparison;
}

export async function updateComparisonComment(
  workspaceId: string,
  comparisonId: string,
  commentId: string,
  body: string,
): Promise<Comparison> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons/${comparisonId}/comments/${commentId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    },
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Comparison;
}

export async function deleteComparisonComment(
  workspaceId: string,
  comparisonId: string,
  commentId: string,
): Promise<Comparison> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons/${comparisonId}/comments/${commentId}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Comparison;
}

export async function getComparisonAudit(
  workspaceId: string,
  comparisonId: string,
): Promise<ComparisonAuditTrail> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons/${comparisonId}/audit`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as ComparisonAuditTrail;
}

export async function recordComparisonClauseOpened(
  workspaceId: string,
  comparisonId: string,
  clauseId: string,
): Promise<ComparisonAuditTrail> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons/${comparisonId}/audit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "CLAUSE_OPENED",
        clause_id: clauseId,
      }),
    },
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as ComparisonAuditTrail;
}

export async function deleteComparison(
  workspaceId: string,
  comparisonId: string,
): Promise<void> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/comparisons/${comparisonId}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw await parseApiError(response);
}
