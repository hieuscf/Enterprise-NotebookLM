/**
 * =============================================================================
 * File: cookies.ts
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: httpOnly cookie helpers for access/refresh tokens (Next.js BFF).
 * Responsibilities:
 *   - Read/write/clear auth cookies from Route Handlers
 * Dependencies:
 *   - next/headers cookies()
 * Public Exports:
 *   - ACCESS_COOKIE, REFRESH_COOKIE, setAuthCookies, clearAuthCookies, getAccessToken, getRefreshToken
 * Database/Table: N/A
 * Related Modules: app/api/auth/*, middleware.ts
 * Important Notes:
 *   - Prefer httpOnly cookies over localStorage for access tokens (XSS mitigation).
 *   - Tokens are never exposed to client JS.
 * =============================================================================
 */

import { cookies } from "next/headers";

export const ACCESS_COOKIE = "enlm_access_token";
export const REFRESH_COOKIE = "enlm_refresh_token";

const baseCookie = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

export async function setAuthCookies(tokens: {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  refresh_max_age_seconds?: number;
}): Promise<void> {
  const jar = await cookies();
  const refreshMax =
    tokens.refresh_max_age_seconds ??
    Number(process.env.REFRESH_TOKEN_EXPIRE_DAYS ?? 7) * 24 * 60 * 60;

  jar.set(ACCESS_COOKIE, tokens.access_token, {
    ...baseCookie,
    maxAge: tokens.expires_in,
  });
  jar.set(REFRESH_COOKIE, tokens.refresh_token, {
    ...baseCookie,
    maxAge: refreshMax,
  });
}

export async function clearAuthCookies(): Promise<void> {
  const jar = await cookies();
  jar.set(ACCESS_COOKIE, "", { ...baseCookie, maxAge: 0 });
  jar.set(REFRESH_COOKIE, "", { ...baseCookie, maxAge: 0 });
}

export async function getAccessToken(): Promise<string | undefined> {
  const jar = await cookies();
  return jar.get(ACCESS_COOKIE)?.value;
}

export async function getRefreshToken(): Promise<string | undefined> {
  const jar = await cookies();
  return jar.get(REFRESH_COOKIE)?.value;
}
