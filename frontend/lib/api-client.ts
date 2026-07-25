/**
 * =============================================================================
 * File: api-client.ts
 * Module/Service: Web App
 * Layer: UI
 * Purpose: Central HTTP client for backend calls via Next.js BFF proxy.
 * Responsibilities:
 *   - Call same-origin /api/proxy and /api/auth/* (httpOnly cookies)
 *   - On 401 from proxy, attempt /api/auth/refresh once then retry / redirect login
 *   - Workspace CRUD helpers (FR1) + Workspace Member helpers (UC10)
 * Dependencies:
 *   - Next.js Route Handlers under app/api
 * Public Exports:
 *   - apiFetch, authLogin, authLogout, authMe, authRefresh
 *   - listWorkspaces, getWorkspace, createWorkspace, updateWorkspace, deleteWorkspace
 *   - listWorkspaceMembers, addWorkspaceMember, updateWorkspaceMemberRole, removeWorkspaceMember
 *   - ApiClientError, parseApiError
 * Database/Table: N/A
 * Related Modules: types/auth, types/workspaces, hooks/useAuth
 * Important Notes:
 *   - Tokens live in httpOnly cookies — never localStorage for access tokens.
 *   - Frontend must NEVER call LLM providers directly.
 * =============================================================================
 */

import type { User } from "@/types/auth";
import type {
  AddMemberInput,
  UpdateMemberRoleInput,
  Workspace,
  WorkspaceCreateInput,
  WorkspaceListResponse,
  WorkspaceMember,
  WorkspaceUpdateInput,
} from "@/types/workspaces";

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
  }
}

/** Parse FastAPI ErrorResponse nested under `detail` (or plain message). */
export async function parseApiError(response: Response): Promise<ApiClientError> {
  const fallback = new ApiClientError(
    response.status,
    "error",
    `Request failed (${response.status})`,
  );
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (detail && typeof detail === "object" && typeof detail.message === "string") {
      return new ApiClientError(
        response.status,
        typeof detail.code === "string" ? detail.code : "error",
        detail.message,
      );
    }
    if (typeof detail === "string") {
      return new ApiClientError(response.status, "error", detail);
    }
    if (typeof payload?.message === "string") {
      return new ApiClientError(
        response.status,
        typeof payload.code === "string" ? payload.code : "error",
        payload.message,
      );
    }
  } catch {
    /* ignore JSON parse errors */
  }
  return fallback;
}

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

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    throw await parseApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
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

// ---------------------------------------------------------------------------
// Workspaces (FR1)
// ---------------------------------------------------------------------------

export async function listWorkspaces(
  page = 1,
  pageSize = 20,
): Promise<WorkspaceListResponse> {
  return apiJson<WorkspaceListResponse>(
    `/workspaces?page=${page}&page_size=${pageSize}`,
  );
}

export async function getWorkspace(workspaceId: string): Promise<Workspace> {
  return apiJson<Workspace>(`/workspaces/${workspaceId}`);
}

export async function createWorkspace(
  input: WorkspaceCreateInput,
): Promise<Workspace> {
  return apiJson<Workspace>("/workspaces", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateWorkspace(
  workspaceId: string,
  input: WorkspaceUpdateInput,
): Promise<Workspace> {
  return apiJson<Workspace>(`/workspaces/${workspaceId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await apiJson<void>(`/workspaces/${workspaceId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Workspace Members (UC10)
// ---------------------------------------------------------------------------

export async function listWorkspaceMembers(
  workspaceId: string,
): Promise<WorkspaceMember[]> {
  return apiJson<WorkspaceMember[]>(`/workspaces/${workspaceId}/members`);
}

export async function addWorkspaceMember(
  workspaceId: string,
  input: AddMemberInput,
): Promise<WorkspaceMember> {
  return apiJson<WorkspaceMember>(`/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateWorkspaceMemberRole(
  workspaceId: string,
  userId: string,
  input: UpdateMemberRoleInput,
): Promise<WorkspaceMember> {
  return apiJson<WorkspaceMember>(
    `/workspaces/${workspaceId}/members/${userId}`,
    { method: "PATCH", body: JSON.stringify(input) },
  );
}

export async function removeWorkspaceMember(
  workspaceId: string,
  userId: string,
): Promise<void> {
  await apiJson<void>(`/workspaces/${workspaceId}/members/${userId}`, {
    method: "DELETE",
  });
}
