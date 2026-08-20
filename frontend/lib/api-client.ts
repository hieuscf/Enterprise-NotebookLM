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
 *   - Document upload (XHR, progress-capable) + pipeline-status polling (FR2)
 *   - Document/version list, detail, set-current (FR2 Part 2)
 * Dependencies:
 *   - Next.js Route Handlers under app/api
 * Public Exports:
 *   - apiFetch, authLogin, authLogout, authMe, authRefresh
 *   - listWorkspaces, getWorkspace, createWorkspace, updateWorkspace, deleteWorkspace
 *   - listWorkspaceMembers, listWorkspaceMemberCandidates, addWorkspaceMember,
 *     updateWorkspaceMemberRole, removeWorkspaceMember
 *   - listAdminUsers, createAdminUser, deleteAdminUser
 *   - uploadDocumentXhr, uploadDocumentVersionXhr, getPipelineStatus
 *   - listDocuments, getDocument, listDocumentVersions, getDocumentVersion, setCurrentVersion
 *   - ApiClientError, parseApiError
 * Database/Table: N/A
 * Related Modules: types/auth, types/workspaces, types/documents, hooks/useAuth
 * Important Notes:
 *   - Tokens live in httpOnly cookies — never localStorage for access tokens.
 *   - Frontend must NEVER call LLM providers directly.
 * =============================================================================
 */

import type { User } from "@/types/auth";
import type {
  AdminUserCreated,
  AdminUserListResponse,
  CreateAdminUserInput,
} from "@/types/admin";
import type {
  Document,
  DocumentChunkListResponse,
  DocumentListResponse,
  DocumentVersion,
  FileType,
  PipelineRun,
} from "@/types/documents";
import type {
  AddMemberInput,
  MemberCandidate,
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
      // Clear stale cookies first — otherwise middleware treats empty session as
      // authenticated and can bounce /login ↔ protected pages forever.
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      }).catch(() => undefined);
      const next = `${window.location.pathname}${window.location.search}`;
      window.location.assign(`/login?next=${encodeURIComponent(next)}`);
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
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new ApiClientError(
      response.status,
      "invalid_response",
      "Server returned a non-JSON response",
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiClientError(
      response.status,
      "invalid_response",
      "Server returned invalid JSON",
    );
  }
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
  try {
    const response = await fetch("/api/auth/me", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    const contentType = response.headers.get("Content-Type") ?? "";
    if (!contentType.includes("application/json")) return null;
    return (await response.json()) as User;
  } catch {
    return null;
  }
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

export async function listWorkspaceMemberCandidates(
  workspaceId: string,
  params?: { q?: string; limit?: number },
): Promise<MemberCandidate[]> {
  const qs = new URLSearchParams();
  if (params?.q?.trim()) qs.set("q", params.q.trim());
  if (params?.limit != null) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiJson<MemberCandidate[]>(
    `/workspaces/${workspaceId}/member-candidates${suffix}`,
  );
}

export async function addWorkspaceMember(
  workspaceId: string,
  input: AddMemberInput,
): Promise<WorkspaceMember> {
  const body: Record<string, string> = { role: input.role };
  if (input.user_id) body.user_id = input.user_id;
  if (input.email) body.email = input.email;
  return apiJson<WorkspaceMember>(`/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: JSON.stringify(body),
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

// ---------------------------------------------------------------------------
// Admin Users (FR12 — POST/GET/DELETE /admin/users)
// ---------------------------------------------------------------------------

export async function listAdminUsers(): Promise<AdminUserListResponse> {
  return apiJson<AdminUserListResponse>("/admin/users");
}

export async function createAdminUser(
  input: CreateAdminUserInput,
): Promise<AdminUserCreated> {
  return apiJson<AdminUserCreated>("/admin/users", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function deleteAdminUser(userId: string): Promise<void> {
  await apiJson<void>(`/admin/users/${userId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Documents — upload & pipeline status (FR2)
// ---------------------------------------------------------------------------

export type UploadProgressHandler = (percent: number) => void;

function mapUploadErrorBody(status: number, body: unknown): ApiClientError {
  if (body && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
      const d = detail as { code?: unknown; message: string };
      return new ApiClientError(status, typeof d.code === "string" ? d.code : "error", d.message);
    }
    if (typeof detail === "string") {
      return new ApiClientError(status, "error", detail);
    }
  }
  if (status === 413) {
    return new ApiClientError(413, "payload_too_large", "File vượt quá kích thước cho phép của hệ thống.");
  }
  if (status === 415) {
    return new ApiClientError(415, "unsupported_file_type", "Định dạng file không được hỗ trợ.");
  }
  return new ApiClientError(status, "error", `Yêu cầu thất bại (${status})`);
}

function xhrUploadOnce(
  workspaceId: string,
  file: File,
  title: string,
  onProgress?: UploadProgressHandler,
): { xhr: XMLHttpRequest; promise: Promise<{ status: number; body: unknown }> } {
  const xhr = new XMLHttpRequest();
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title);

  const promise = new Promise<{ status: number; body: unknown }>((resolve, reject) => {
    xhr.open("POST", `/api/proxy/workspaces/${workspaceId}/documents`);
    xhr.withCredentials = true;
    xhr.responseType = "text";

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      let body: unknown;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch {
        body = undefined;
      }
      resolve({ status: xhr.status, body });
    };
    xhr.onerror = () =>
      reject(new ApiClientError(0, "network_error", "Mất kết nối mạng khi đang tải lên."));
    xhr.onabort = () => reject(new ApiClientError(0, "aborted", "Đã hủy tải lên."));

    xhr.send(formData);
  });

  return { xhr, promise };
}

/**
 * Uploads a new document via XHR (needed for upload progress events; `fetch`
 * has no upload-progress API). Retries once on 401 via the same cookie-based
 * refresh flow used by `apiFetch`.
 */
export function uploadDocumentXhr(
  workspaceId: string,
  file: File,
  title: string,
  onProgress?: UploadProgressHandler,
): { promise: Promise<DocumentVersion>; abort: () => void } {
  let currentXhr: XMLHttpRequest | null = null;

  const attempt = async (allowRefresh: boolean): Promise<DocumentVersion> => {
    const { xhr, promise } = xhrUploadOnce(workspaceId, file, title, onProgress);
    currentXhr = xhr;
    const { status, body } = await promise;
    if (status === 202) return body as DocumentVersion;
    if (status === 401 && allowRefresh) {
      const refreshed = await tryRefreshSession();
      if (refreshed) return attempt(false);
    }
    throw mapUploadErrorBody(status, body);
  };

  return {
    promise: attempt(true),
    abort: () => currentXhr?.abort(),
  };
}

export async function getPipelineStatus(
  workspaceId: string,
  documentId: string,
  versionId: string,
): Promise<PipelineRun> {
  return apiJson<PipelineRun>(
    `/workspaces/${workspaceId}/documents/${documentId}/versions/${versionId}/pipeline-status`,
  );
}

/**
 * Uploads a replacement version for an existing document via XHR (progress
 * events). No `title` field — POST .../versions only accepts `file` per the
 * OpenAPI contract; the document keeps its original title.
 */
export function uploadDocumentVersionXhr(
  workspaceId: string,
  documentId: string,
  file: File,
  onProgress?: UploadProgressHandler,
): { promise: Promise<DocumentVersion>; abort: () => void } {
  let currentXhr: XMLHttpRequest | null = null;

  const sendOnce = (): { xhr: XMLHttpRequest; promise: Promise<{ status: number; body: unknown }> } => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    const promise = new Promise<{ status: number; body: unknown }>((resolve, reject) => {
      xhr.open(
        "POST",
        `/api/proxy/workspaces/${workspaceId}/documents/${documentId}/versions`,
      );
      xhr.withCredentials = true;
      xhr.responseType = "text";

      xhr.upload.onprogress = (event) => {
        if (onProgress && event.lengthComputable) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };

      xhr.onload = () => {
        let body: unknown;
        try {
          body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
        } catch {
          body = undefined;
        }
        resolve({ status: xhr.status, body });
      };
      xhr.onerror = () =>
        reject(new ApiClientError(0, "network_error", "Mất kết nối mạng khi đang tải lên."));
      xhr.onabort = () => reject(new ApiClientError(0, "aborted", "Đã hủy tải lên."));

      xhr.send(formData);
    });

    return { xhr, promise };
  };

  const attempt = async (allowRefresh: boolean): Promise<DocumentVersion> => {
    const { xhr, promise } = sendOnce();
    currentXhr = xhr;
    const { status, body } = await promise;
    if (status === 202) return body as DocumentVersion;
    if (status === 401 && allowRefresh) {
      const refreshed = await tryRefreshSession();
      if (refreshed) return attempt(false);
    }
    throw mapUploadErrorBody(status, body);
  };

  return {
    promise: attempt(true),
    abort: () => currentXhr?.abort(),
  };
}

// ---------------------------------------------------------------------------
// Documents — list, detail, version history, set-current (FR2 Part 2)
// ---------------------------------------------------------------------------

export async function listDocuments(
  workspaceId: string,
  options?: { page?: number; pageSize?: number; fileType?: FileType | null },
): Promise<DocumentListResponse> {
  const params = new URLSearchParams({
    page: String(options?.page ?? 1),
    page_size: String(options?.pageSize ?? 20),
  });
  if (options?.fileType) params.set("file_type", options.fileType);
  return apiJson<DocumentListResponse>(
    `/workspaces/${workspaceId}/documents?${params.toString()}`,
  );
}

export async function getDocument(
  workspaceId: string,
  documentId: string,
): Promise<Document> {
  return apiJson<Document>(`/workspaces/${workspaceId}/documents/${documentId}`);
}

/** DELETE /workspaces/{id}/documents/{documentId} — removes document + versions (204). */
export async function deleteDocument(
  workspaceId: string,
  documentId: string,
): Promise<void> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/documents/${documentId}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw await parseApiError(response);
}

export async function listDocumentChunks(
  workspaceId: string,
  documentId: string,
  versionId?: string | null,
): Promise<DocumentChunkListResponse> {
  const qs =
    versionId && versionId.trim()
      ? `?versionId=${encodeURIComponent(versionId)}`
      : "";
  return apiJson<DocumentChunkListResponse>(
    `/workspaces/${workspaceId}/documents/${documentId}/chunks${qs}`,
  );
}

/** Canonical Knowledge Document (Markdown + blocks) for Knowledge View. */
export async function getCanonicalDocument(
  workspaceId: string,
  documentId: string,
  versionId?: string | null,
): Promise<import("@/types/canonical").CanonicalDocument> {
  const qs =
    versionId && versionId.trim()
      ? `?versionId=${encodeURIComponent(versionId)}`
      : "";
  return apiJson(
    `/workspaces/${workspaceId}/documents/${documentId}/canonical${qs}`,
  );
}

/** Same-origin URL for original/preview PDF bytes (BFF proxy + cookies). */
export function documentContentUrl(
  workspaceId: string,
  documentId: string,
  options?: { versionId?: string | null; download?: boolean },
): string {
  const params = new URLSearchParams();
  if (options?.versionId) params.set("versionId", options.versionId);
  if (options?.download) params.set("download", "true");
  const qs = params.toString();
  const path = `/workspaces/${workspaceId}/documents/${documentId}/content`;
  return `/api/proxy${path}${qs ? `?${qs}` : ""}`;
}

export async function listDocumentVersions(
  workspaceId: string,
  documentId: string,
): Promise<DocumentVersion[]> {
  return apiJson<DocumentVersion[]>(
    `/workspaces/${workspaceId}/documents/${documentId}/versions`,
  );
}

export async function getDocumentVersion(
  workspaceId: string,
  documentId: string,
  versionId: string,
): Promise<DocumentVersion> {
  return apiJson<DocumentVersion>(
    `/workspaces/${workspaceId}/documents/${documentId}/versions/${versionId}`,
  );
}

export async function setCurrentVersion(
  workspaceId: string,
  documentId: string,
  versionId: string,
): Promise<Document> {
  return apiJson<Document>(
    `/workspaces/${workspaceId}/documents/${documentId}/versions/${versionId}/set-current`,
    { method: "POST" },
  );
}
