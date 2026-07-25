/**
 * =============================================================================
 * File: backend.ts
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Server-side helper to call backend-api from Next.js Route Handlers.
 * Responsibilities:
 *   - Resolve internal backend base URL (Docker vs local)
 *   - Perform JSON fetch to auth / proxied endpoints
 * Dependencies:
 *   - API_INTERNAL_BASE_URL / NEXT_PUBLIC_API_BASE_URL
 * Public Exports:
 *   - getBackendBaseUrl, backendFetch
 * Database/Table: N/A
 * Related Modules: app/api/auth/*, app/api/proxy/*
 * Important Notes: Server routes must use Docker hostname backend-api when in Compose.
 * =============================================================================
 */

export function getBackendBaseUrl(): string {
  const url =
    process.env.API_INTERNAL_BASE_URL?.replace(/\/$/, "") ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
    "http://localhost:8000";
  return url;
}

export async function backendFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const url = `${getBackendBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  return fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
}
