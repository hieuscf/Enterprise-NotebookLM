/**
 * =============================================================================
 * File: route.ts (GET /api/auth/me)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: BFF proxy for GET /auth/me using httpOnly access cookie.
 * Responsibilities:
 *   - Attach Bearer from cookie; optionally refresh once on 401
 * Dependencies:
 *   - lib/auth/backend, lib/auth/cookies, lib/auth/refresh
 * Public Exports:
 *   - GET
 * Database/Table: N/A
 * Related Modules: hooks/useAuth, hooks/useWorkspaceRole
 * Important Notes: Always reflects live roles from DB via backend /auth/me.
 * =============================================================================
 */

import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/auth/backend";
import { clearAuthCookies, getAccessToken } from "@/lib/auth/cookies";
import { refreshAccessToken } from "@/lib/auth/refresh";
import type { User } from "@/types/auth";

export async function GET() {
  let access = await getAccessToken();
  if (!access) {
    access = (await refreshAccessToken()) ?? undefined;
  }
  if (!access) {
    await clearAuthCookies();
    return NextResponse.json(
      { code: "unauthorized", message: "Unauthorized" },
      { status: 401 },
    );
  }

  let upstream = await backendFetch("/auth/me", {
    headers: { Authorization: `Bearer ${access}` },
  });

  if (upstream.status === 401) {
    const refreshed = await refreshAccessToken();
    if (!refreshed) {
      await clearAuthCookies();
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
