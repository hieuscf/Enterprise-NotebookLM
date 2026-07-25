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
    // Already signed in → skip login page
    if (pathname === "/login" || pathname.startsWith("/login/")) {
      const hasSession =
        Boolean(request.cookies.get(ACCESS_COOKIE)?.value) ||
        Boolean(request.cookies.get(REFRESH_COOKIE)?.value);
      if (hasSession) {
        return NextResponse.redirect(new URL("/", request.url));
      }
    }
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
