/**
 * =============================================================================
 * File: refresh.ts
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Single-flight BFF refresh so concurrent proxy 401s do not race-rotate.
 * Responsibilities:
 *   - Deduplicate in-process /auth/refresh calls
 *   - Set httpOnly cookies; avoid clearing cookies on lost rotation races
 * Dependencies:
 *   - lib/auth/backend, lib/auth/cookies
 * Public Exports:
 *   - refreshAccessToken
 * Database/Table: N/A
 * Related Modules: app/api/proxy, app/api/auth/refresh, app/api/auth/me
 * Important Notes:
 *   - Backend rotates refresh jti; concurrent tryRefresh with the same cookie
 *     used to clear a just-rotated session (HTTP 401 on PDF/content).
 *   - Module-level lock covers one Node process (Compose / single instance).
 * =============================================================================
 */

import { backendFetch } from "@/lib/auth/backend";
import {
  clearAuthCookies,
  getAccessToken,
  getRefreshToken,
  setAuthCookies,
} from "@/lib/auth/cookies";
import type { AuthToken } from "@/types/auth";

let refreshInFlight: Promise<string | null> | null = null;

/**
 * Rotate tokens via backend `/auth/refresh`. Concurrent callers share one flight
 * and receive the same new access token (or null on hard failure).
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function performRefresh(): Promise<string | null> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    // Another concurrent refresh may already have set a new access cookie.
    return (await getAccessToken()) ?? null;
  }

  const upstream = await backendFetch("/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!upstream.ok) {
    // Lost rotation race: sibling request already rotated; reuse its access cookie.
    const raced = await getAccessToken();
    if (raced) return raced;
    await clearAuthCookies();
    return null;
  }

  const tokens = (await upstream.json()) as AuthToken;
  await setAuthCookies({
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
    expires_in: tokens.expires_in,
  });
  return tokens.access_token;
}
