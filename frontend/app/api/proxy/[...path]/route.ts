/**
 * =============================================================================
 * File: route.ts (/api/proxy/[...path])
 * Module/Service: Web App / API Gateway (BFF)
 * Layer: UI
 * Purpose: Same-origin proxy so browser never holds JWT in JS (httpOnly cookies).
 * Responsibilities:
 *   - Forward method/body/query to backend with Authorization from access cookie
 *   - On 401, attempt refresh once then retry
 * Dependencies:
 *   - lib/auth/backend, lib/auth/cookies
 * Public Exports:
 *   - GET, POST, PUT, PATCH, DELETE
 * Database/Table: N/A
 * Related Modules: lib/api-client.ts
 * Important Notes: Frontend must call /api/proxy/* — never LLM providers directly.
 * =============================================================================
 */

import { NextRequest, NextResponse } from "next/server";

import { backendFetch } from "@/lib/auth/backend";
import {
  clearAuthCookies,
  getAccessToken,
  getRefreshToken,
  setAuthCookies,
} from "@/lib/auth/cookies";
import type { AuthToken } from "@/types/auth";

type RouteContext = { params: Promise<{ path: string[] }> };

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

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const targetPath = `/${path.join("/")}${request.nextUrl.search}`;

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

  const outboundHeaders: Record<string, string> = {
    Authorization: `Bearer ${access}`,
    Accept: request.headers.get("Accept") ?? "application/json",
  };
  const requestContentType = request.headers.get("Content-Type");
  if (requestContentType) outboundHeaders["Content-Type"] = requestContentType;

  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.arrayBuffer();
  }

  const buildInit = (token: string): RequestInit => ({
    method: request.method,
    headers: { ...outboundHeaders, Authorization: `Bearer ${token}` },
    body,
  });

  let upstream = await backendFetch(targetPath, buildInit(access));

  if (upstream.status === 401) {
    const refreshed = await tryRefresh();
    if (!refreshed) {
      return NextResponse.json(
        { code: "unauthorized", message: "Unauthorized" },
        { status: 401 },
      );
    }
    upstream = await backendFetch(targetPath, buildInit(refreshed));
  }

  const responseHeaders = new Headers();
  const responseContentType = upstream.headers.get("Content-Type");
  if (responseContentType) responseHeaders.set("Content-Type", responseContentType);
  const contentDisposition = upstream.headers.get("Content-Disposition");
  if (contentDisposition) responseHeaders.set("Content-Disposition", contentDisposition);
  const viewerKind = upstream.headers.get("X-Viewer-Kind");
  if (viewerKind) responseHeaders.set("X-Viewer-Kind", viewerKind);
  const retryAfter = upstream.headers.get("Retry-After");
  if (retryAfter) responseHeaders.set("Retry-After", retryAfter);

  const buffer = await upstream.arrayBuffer();
  return new NextResponse(buffer, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
