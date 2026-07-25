/**
 * =============================================================================
 * File: route.ts (POST /api/auth/login)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: BFF login — proxy backend /auth/login and set httpOnly cookies.
 * Responsibilities:
 *   - Forward email/password to backend-api
 *   - Persist access + refresh tokens in httpOnly cookies
 * Dependencies:
 *   - lib/auth/backend, lib/auth/cookies
 * Public Exports:
 *   - POST
 * Database/Table: N/A
 * Related Modules: features/auth/LoginForm, docs OpenAPI AuthToken
 * Important Notes: Public route — excluded from auth middleware matcher.
 * =============================================================================
 */

import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/auth/backend";
import { setAuthCookies } from "@/lib/auth/cookies";
import type { AuthToken } from "@/types/auth";

export async function POST(request: Request) {
  let body: { email?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { code: "invalid_body", message: "Invalid JSON body" },
      { status: 400 },
    );
  }

  if (!body.email || !body.password) {
    return NextResponse.json(
      { code: "invalid_body", message: "Email and password are required" },
      { status: 400 },
    );
  }

  const upstream = await backendFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: body.email, password: body.password }),
  });

  const payload = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(
      {
        code: "unauthorized",
        message:
          typeof payload?.detail === "string"
            ? payload.detail
            : "Invalid email or password",
      },
      { status: upstream.status === 401 ? 401 : upstream.status },
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
