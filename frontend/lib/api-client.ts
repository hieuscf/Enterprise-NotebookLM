/**
 * =============================================================================
 * File: api-client.ts
 * Module/Service: Web App
 * Layer: UI
 * Purpose: Central HTTP client for all backend API calls from the frontend.
 * Responsibilities:
 *   - Provide a single entrypoint for fetch/API requests to backend-api
 *   - Read NEXT_PUBLIC_API_BASE_URL from environment
 * Dependencies:
 *   - Backend OpenAPI contract
 * Public Exports:
 *   - apiBaseUrl, apiFetch
 * Database/Table: N/A
 * Related Modules: frontend/types, docs/Enterprise notebooklm openapi.yaml
 * Important Notes: Frontend must NEVER call LLM providers directly.
 * =============================================================================
 */

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const url = `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  return fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
}
