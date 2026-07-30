/**
 * =============================================================================
 * File: middleware.ts
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Next.js edge middleware — redirect unauthenticated users to /login.
 * Responsibilities:
 *   - Allow public auth routes and static assets
 *   - Require access or refresh httpOnly cookie for protected pages
 * Dependencies:
 *   - next/server
 * Public Exports:
 *   - middleware, config
 * Database/Table: N/A
 * Related Modules: lib/auth/cookies (cookie names), app/login
 * Important Notes: Cookie presence only — JWT signature verified by backend/BFF.
 *   Never redirect /login → / based on cookies alone (stale tokens cause loops).
 * =============================================================================
 */

import { NextRequest, NextResponse } from "next/server";

const ACCESS_COOKIE = "enlm_access_token";
const REFRESH_COOKIE = "enlm_refresh_token";

const PUBLIC_PREFIXES = [
  "/login",
  "/logout",
  "/api/auth/login",
  "/api/auth/refresh",
  "/api/auth/logout",
  "/_next",
  "/favicon.ico",
];

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (isPublic(pathname)) {
    // Do NOT bounce /login → / just because cookies exist.
    // Stale access/refresh cookies would create an infinite redirect loop with
    // client 401 → /login (middleware sees cookies → / → 401 → …).
    return NextResponse.next();
  }

  const hasSession =
    Boolean(request.cookies.get(ACCESS_COOKIE)?.value) ||
    Boolean(request.cookies.get(REFRESH_COOKIE)?.value);

  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except static files commonly served by Next.
     */
    "/((?!_next/static|_next/image|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
