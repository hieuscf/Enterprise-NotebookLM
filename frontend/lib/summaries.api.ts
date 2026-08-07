/**
 * =============================================================================
 * File: summaries.api.ts
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: Typed calls to /workspaces/{id}/…/summaries (FR6).
 * Responsibilities:
 *   - listDocumentSummaries / createDocumentSummary / getSummary / deleteSummary
 * Dependencies:
 *   - lib/api-client (apiFetch, parseApiError)
 * Public Exports:
 *   - listDocumentSummaries, createDocumentSummary, getSummary, deleteSummary
 * Database/Table: N/A (talks to summaries via API)
 * Related Modules: hooks/useDocumentSummaries, features/summaries/*
 * Important Notes: POST returns 202 with status=processing — FE must poll.
 * =============================================================================
 */

import { apiFetch, parseApiError } from "@/lib/api-client";
import type { Summary, SummaryCreateRequest } from "@/types/summaries";

export async function listDocumentSummaries(
  workspaceId: string,
  documentId: string,
): Promise<Summary[]> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/documents/${documentId}/summaries`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Summary[];
}

export async function createDocumentSummary(
  workspaceId: string,
  documentId: string,
  body: SummaryCreateRequest,
): Promise<Summary> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/documents/${documentId}/summaries`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Summary;
}

export async function getSummary(
  workspaceId: string,
  summaryId: string,
): Promise<Summary> {
  const response = await apiFetch(`/workspaces/${workspaceId}/summaries/${summaryId}`);
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Summary;
}

export async function deleteSummary(
  workspaceId: string,
  summaryId: string,
): Promise<void> {
  const response = await apiFetch(`/workspaces/${workspaceId}/summaries/${summaryId}`, {
    method: "DELETE",
  });
  if (!response.ok) throw await parseApiError(response);
}
