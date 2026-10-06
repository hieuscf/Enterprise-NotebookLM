/**
 * =============================================================================
 * File: route.ts (POST /api/auth/refresh)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: BFF refresh — rotate tokens using httpOnly refresh cookie.
 * Responsibilities:
 *   - Single-flight refresh via lib/auth/refresh (shared with proxy)
 * Dependencies:
 *   - lib/auth/refresh
 * Public Exports:
 *   - POST
 * Database/Table: N/A
 * Related Modules: lib/api-client (401 retry), middleware, /api/proxy
 * Important Notes: Must share refresh flight with proxy to avoid jti races.
 * =============================================================================
 */

import { NextResponse } from "next/server";

import { refreshAccessToken } from "@/lib/auth/refresh";

export async function POST() {
  const access = await refreshAccessToken();
  if (!access) {
    return NextResponse.json(
      { code: "unauthorized", message: "Invalid or expired refresh token" },
      { status: 401 },
    );
  }

  return NextResponse.json({
    token_type: "bearer",
    ok: true,
  });
}
