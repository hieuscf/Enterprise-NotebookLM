/**
 * =============================================================================
 * File: comparisons.api.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Typed calls to /workspaces/{id}/comparisons (FR8).
 * Responsibilities:
 *   - list / create / get / delete Comparisons
 * Dependencies:
 *   - lib/api-client (apiFetch, parseApiError)
 * Public Exports:
 *   - listComparisons, createComparison, getComparison, deleteComparison
 * Database/Table: N/A
 * Related Modules: hooks/useComparisons, features/comparisons/*
 * Important Notes: POST returns 202 with status=processing — FE must poll.
 * =============================================================================
 */

import { apiFetch, parseApiError } from "@/lib/api-client";
import type {
  Comparison,
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
