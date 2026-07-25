/**
 * =============================================================================
 * File: route.ts (GET /api/auth/me)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: BFF proxy for GET /auth/me using httpOnly access cookie.
 * Responsibilities:
 *   - Attach Bearer from cookie; optionally refresh once on 401
 * Dependencies:
 *   - lib/auth/backend, lib/auth/cookies
 * Public Exports:
 *   - GET
 * Database/Table: N/A
 * Related Modules: hooks/useAuth, hooks/useWorkspaceRole
 * Important Notes: Always reflects live roles from DB via backend /auth/me.
 * =============================================================================
 */

import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/auth/backend";
import {
  clearAuthCookies,
  getAccessToken,
  getRefreshToken,
  setAuthCookies,
} from "@/lib/auth/cookies";
import type { AuthToken, User } from "@/types/auth";

async function tryRefresh(): Promise<string | null> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) return null;

  const upstream = await backendFetch("/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!upstream.ok) {
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

export async function GET() {
  let access = await getAccessToken();
  if (!access) {
    access = (await tryRefresh()) ?? undefined;
  }
  if (!access) {
    return NextResponse.json(
      { code: "unauthorized", message: "Unauthorized" },
      { status: 401 },
    );
  }

  let upstream = await backendFetch("/auth/me", {
    headers: { Authorization: `Bearer ${access}` },
  });

  if (upstream.status === 401) {
    const refreshed = await tryRefresh();
    if (!refreshed) {
      return NextResponse.json(
        { code: "unauthorized", message: "Unauthorized" },
        { status: 401 },
      );
    }
    upstream = await backendFetch("/auth/me", {
      headers: { Authorization: `Bearer ${refreshed}` },
    });
  }

  const payload = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(
      { code: "unauthorized", message: "Unauthorized" },
      { status: upstream.status },
    );
  }

  return NextResponse.json(payload as User);
}
