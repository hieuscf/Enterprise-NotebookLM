/**
 * =============================================================================
 * File: route.ts (/api/proxy/[...path])
 * Module/Service: Web App / API Gateway (BFF)
 * Layer: UI
 * Purpose: Same-origin proxy so browser never holds JWT in JS (httpOnly cookies).
 * Responsibilities:
 *   - Forward method/body/query to backend with Authorization from access cookie
 *   - On 401, attempt refresh once then retry
 *   - Pipe text/event-stream responses through unbuffered (Chat SSE, FR4)
 * Dependencies:
 *   - lib/auth/backend, lib/auth/cookies
 * Public Exports:
 *   - GET, POST, PUT, PATCH, DELETE
 * Database/Table: N/A
 * Related Modules: lib/api-client.ts, lib/chat.api.ts (SSE streaming)
 * Important Notes:
 *   - Frontend must call /api/proxy/* — never LLM providers directly.
 *   - SSE branch must not buffer the body (defeats streaming); everything
 *     else keeps the original arrayBuffer() behavior unchanged.
 *   - Streaming fetches use undici bodyTimeout=0 to avoid UND_ERR_BODY_TIMEOUT.
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

/** Allow long Chat SSE on platforms that honor route segment config. */
export const runtime = "nodejs";
export const maxDuration = 800;
export const dynamic = "force-dynamic";

function wantsEventStream(request: NextRequest, path: string[]): boolean {
  const accept = (request.headers.get("Accept") ?? "").toLowerCase();
  if (accept.includes("text/event-stream")) return true;
  // POST .../chat/sessions/{id}/messages defaults to SSE in the Chat API.
  if (
    request.method === "POST" &&
    path.includes("chat") &&
    path.includes("sessions") &&
    path[path.length - 1] === "messages"
  ) {
    return true;
  }
  return false;
}

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
  const streaming = wantsEventStream(request, path);

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

  let upstream = await backendFetch(targetPath, buildInit(access), { streaming });

  if (upstream.status === 401) {
    const refreshed = await tryRefresh();
    if (!refreshed) {
      return NextResponse.json(
        { code: "unauthorized", message: "Unauthorized" },
        { status: 401 },
      );
    }
    upstream = await backendFetch(targetPath, buildInit(refreshed), { streaming });
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

  // Chat streaming (SSE) — pipe the body through as-is; buffering it here
  // would defeat the whole point of streaming (no tokens until the answer
  // finished generating).
  if (
    streaming ||
    responseContentType?.toLowerCase().startsWith("text/event-stream")
  ) {
    responseHeaders.set("Cache-Control", "no-cache, no-transform");
    responseHeaders.set("Connection", "keep-alive");
    responseHeaders.set("X-Accel-Buffering", "no");
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  }

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
