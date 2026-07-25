/**
 * =============================================================================
 * File: route.ts (POST /api/auth/refresh)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: BFF refresh — rotate tokens using httpOnly refresh cookie.
 * Responsibilities:
 *   - Read refresh cookie, call backend /auth/refresh, set new cookies
 * Dependencies:
 *   - lib/auth/backend, lib/auth/cookies
 * Public Exports:
 *   - POST
 * Database/Table: N/A
 * Related Modules: lib/api-client (401 retry), middleware
 * Important Notes: Public enough for unauthenticated access cookie refresh.
 * =============================================================================
 */

import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/auth/backend";
import {
  clearAuthCookies,
  getRefreshToken,
  setAuthCookies,
} from "@/lib/auth/cookies";
import type { AuthToken } from "@/types/auth";

export async function POST() {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    await clearAuthCookies();
    return NextResponse.json(
      { code: "unauthorized", message: "Missing refresh token" },
      { status: 401 },
    );
  }

  const upstream = await backendFetch("/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  const payload = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    await clearAuthCookies();
    return NextResponse.json(
      { code: "unauthorized", message: "Invalid or expired refresh token" },
      { status: 401 },
    );
  }

  const tokens = payload as AuthToken;
  await setAuthCookies({
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
    expires_in: tokens.expires_in,
  });

  return NextResponse.json({
    token_type: tokens.token_type ?? "bearer",
    expires_in: tokens.expires_in,
  });
}
