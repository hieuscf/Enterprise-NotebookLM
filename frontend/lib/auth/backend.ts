/**
 * =============================================================================
 * File: backend.ts
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Server-side helper to call backend-api from Next.js Route Handlers.
 * Responsibilities:
 *   - Resolve internal backend base URL (Docker vs local)
 *   - Perform JSON fetch to auth / proxied endpoints
 *   - Long-running Agent for Chat SSE (no undici body idle timeout)
 * Dependencies:
 *   - API_INTERNAL_BASE_URL / NEXT_PUBLIC_API_BASE_URL, undici
 * Public Exports:
 *   - getBackendBaseUrl, backendFetch
 * Database/Table: N/A
 * Related Modules: app/api/auth/*, app/api/proxy/*
 * Important Notes: Server routes must use Docker hostname backend-api when in Compose.
 *   Chat SSE can idle >300s between tokens — default undici bodyTimeout kills the pipe.
 * =============================================================================
 */

import { Agent } from "undici";

export function getBackendBaseUrl(): string {
  const url =
    process.env.API_INTERNAL_BASE_URL?.replace(/\/$/, "") ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
    "http://localhost:8000";
  return url;
}

/** Default undici bodyTimeout is 300s — SSE chat routinely exceeds that idle gap. */
const streamingAgent = new Agent({
  connectTimeout: 60_000,
  headersTimeout: 600_000,
  bodyTimeout: 0,
  keepAliveTimeout: 600_000,
  keepAliveMaxTimeout: 600_000,
});

export type BackendFetchOptions = {
  /** Disable undici body/header idle timeouts (Chat SSE, long LLM waits). */
  streaming?: boolean;
};

export async function backendFetch(
  path: string,
  init?: RequestInit,
  options?: BackendFetchOptions,
): Promise<Response> {
  const url = `${getBackendBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  return fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
    // undici dispatcher — typed loosely for Next's fetch wrapper
    ...(options?.streaming
      ? ({ dispatcher: streamingAgent } as RequestInit)
      : {}),
  });
}
