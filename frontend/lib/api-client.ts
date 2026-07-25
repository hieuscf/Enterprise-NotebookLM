/**
 * =============================================================================
 * File: api-client.ts
 * Module/Service: Web App
 * Layer: UI
 * Purpose: Central HTTP client for backend calls via Next.js BFF proxy.
 * Responsibilities:
 *   - Call same-origin /api/proxy and /api/auth/* (httpOnly cookies)
 *   - On 401 from proxy, attempt /api/auth/refresh once then retry / redirect login
 * Dependencies:
 *   - Next.js Route Handlers under app/api
 * Public Exports:
 *   - apiFetch, authLogin, authLogout, authMe, authRefresh
 * Database/Table: N/A
 * Related Modules: types/auth, hooks/useAuth
 * Important Notes:
 *   - Tokens live in httpOnly cookies — never localStorage for access tokens.
 *   - Frontend must NEVER call LLM providers directly.
 * =============================================================================
 */

import type { User } from "@/types/auth";

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    })
      .then((res) => res.ok)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/**
 * Authenticated backend call through BFF (`/api/proxy/...`).
 * Cookies are sent automatically (same-origin); JWT never touches localStorage.
 */
export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const url = `/api/proxy${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  let response = await fetch(url, {
    ...init,
    headers,
    credentials: "same-origin",
  });

  if (response.status === 401) {
    const refreshed = await tryRefreshSession();
    if (refreshed) {
      response = await fetch(url, {
        ...init,
        headers,
        credentials: "same-origin",
      });
    } else if (typeof window !== "undefined") {
      window.location.assign("/login");
    }
  }

  return response;
}

export async function authLogin(
  email: string,
  password: string,
): Promise<{ ok: true } | { ok: false; message: string }> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (response.ok) return { ok: true };

  const payload = await response.json().catch(() => ({}));
  const message =
    typeof payload?.message === "string"
      ? payload.message
      : "Đăng nhập thất bại. Kiểm tra email hoặc mật khẩu.";
  return { ok: false, message };
}

export async function authRefresh(): Promise<boolean> {
  return tryRefreshSession();
}

export async function authLogout(): Promise<void> {
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
  });
}

export async function authMe(): Promise<User | null> {
  const response = await fetch("/api/auth/me", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) return null;
  return (await response.json()) as User;
}
