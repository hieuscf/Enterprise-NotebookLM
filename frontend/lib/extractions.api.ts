/**
 * =============================================================================
 * File: extractions.api.ts
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Typed calls to /workspaces/{id}/…/extractions (FR7).
 * Responsibilities:
 *   - list / create / get / delete Extractions
 * Dependencies:
 *   - lib/api-client (apiFetch, parseApiError)
 * Public Exports:
 *   - listDocumentExtractions, createDocumentExtraction, getExtraction,
 *     deleteExtraction
 * Database/Table: N/A
 * Related Modules: hooks/useDocumentExtractions, features/extractions/*
 * Important Notes: POST returns 202 with status=processing — FE must poll.
 * =============================================================================
 */

import { apiFetch, parseApiError } from "@/lib/api-client";
import type { Extraction, ExtractionCreateRequest } from "@/types/extractions";

export async function listDocumentExtractions(
  workspaceId: string,
  documentId: string,
): Promise<Extraction[]> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/documents/${documentId}/extractions`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Extraction[];
}

export async function createDocumentExtraction(
  workspaceId: string,
  documentId: string,
  body: ExtractionCreateRequest,
): Promise<Extraction> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/documents/${documentId}/extractions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Extraction;
}

export async function getExtraction(
  workspaceId: string,
  extractionId: string,
): Promise<Extraction> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/extractions/${extractionId}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as Extraction;
}

export async function deleteExtraction(
  workspaceId: string,
  extractionId: string,
): Promise<void> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/extractions/${extractionId}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw await parseApiError(response);
}
