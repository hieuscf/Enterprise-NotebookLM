/**
 * =============================================================================
 * File: admin.ts
 * Module/Service: Observability / Admin Console (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Admin endpoints matching backend Pydantic /
 *          OpenAPI schemas (query-logs, cost-summary, users, documents).
 * Responsibilities:
 *   - Mirror admin response shapes 1:1 (no invented fields)
 * Dependencies:
 *   - types/chat, types/documents
 * Public Exports:
 *   - QueryLogItem, CostSummary, AdminUser*, AdminDocument*
 * Database/Table: query_logs, message_generations, documents, document_versions
 * Related Modules: lib/admin.api, features/admin/*
 * Important Notes: pipeline-runs reuse PipelineRun from types/documents.ts.
 * =============================================================================
 */

import type { RouteType } from "./chat";
import type {
  DocumentVersion,
  DocumentVersionStatus,
  FileType,
  PipelineRun,
} from "./documents";

/** OpenAPI QueryLog (admin audit row) — matches app/schemas/admin.py QueryLogResponse. */
export type QueryLogItem = {
  id: string;
  user_id: string;
  message_id: string | null;
  cache_id: string | null;
  query_text: string;
  route_type: RouteType;
  llm_calls_count: number;
  model_used: string | null;
  latency_ms: number | null;
  created_at: string;
};

export type CostByModelItem = {
  model_used: string;
  calls: number;
  cost_usd: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};

export type CostByRouteTypeItem = {
  route_type: string;
  count: number;
};

/** Per Micro Agent cost/latency rollup (FR14) — additive, may be empty. */
export type AgentTypeCostSummary = {
  total_cost_usd: number;
  total_latency_ms: number;
  count: number;
  average_latency_ms: number;
};

export type CostSummary = {
  total_cost_usd: number;
  total_llm_calls: number;
  /** Additive — sum(message_generations.prompt_tokens); defaults to 0. */
  total_prompt_tokens: number;
  /** Additive — sum(message_generations.completion_tokens); defaults to 0. */
  total_completion_tokens: number;
  /** Additive — sum(message_generations.total_tokens); defaults to 0. */
  total_tokens: number;
  by_model: CostByModelItem[];
  by_route_type: CostByRouteTypeItem[];
  by_agent_type: Record<string, AgentTypeCostSummary>;
};

/** OpenAPI HealthStatus. */
export type SystemHealthStatus =
  | "healthy"
  | "degraded"
  | "unhealthy"
  | "unknown";

/** OpenAPI HealthServiceCategory. */
export type HealthServiceCategory = "core" | "ai_retrieval";

/** OpenAPI HealthService. */
export type HealthService = {
  id: string;
  name: string;
  category: HealthServiceCategory;
  status: SystemHealthStatus;
  provider: string | null;
  message: string | null;
  checked_at: string;
  response_time_ms: number | null;
  critical: boolean;
};

/** OpenAPI SystemHealth. */
export type SystemHealth = {
  status: SystemHealthStatus;
  checked_at: string;
  message: string | null;
  services: HealthService[];
};

/** OpenAPI CreateAdminUserRequest — plain password; never password_hash. */
export type CreateAdminUserInput = {
  email: string;
  password: string;
  full_name: string;
};

/** OpenAPI AdminUserResponse — create success payload. */
export type AdminUserCreated = {
  id: string;
  email: string;
  full_name: string;
};

/** OpenAPI AdminUserMembership — scoped to caller's admin workspaces. */
export type AdminUserMembershipDto = {
  workspace_id: string;
  workspace_name: string;
  role: "admin" | "editor" | "viewer";
  joined_at: string;
};

/** OpenAPI AdminUserListItem. */
export type AdminUserListItem = {
  user_id: string;
  email: string;
  full_name: string;
  memberships: AdminUserMembershipDto[];
};

/** OpenAPI AdminUserListResponse. */
export type AdminUserListResponse = {
  items: AdminUserListItem[];
};

/** OpenAPI AdminDocumentSummary — counts by current DocumentVersion.status. */
export type AdminDocumentSummary = {
  total: number;
  processing: number;
  ready: number;
  failed: number;
};

/** OpenAPI AdminDocumentListItem. */
export type AdminDocumentListItem = {
  id: string;
  title: string;
  filename: string | null;
  workspace_id: string;
  workspace_name: string;
  file_type: FileType;
  current_version_id: string | null;
  version_number: number | null;
  file_size_bytes: number | null;
  page_count: number | null;
  status: DocumentVersionStatus | null;
  created_at: string;
  updated_at: string;
};

/** OpenAPI AdminDocumentListResponse. */
export type AdminDocumentListResponse = {
  items: AdminDocumentListItem[];
  page: number;
  page_size: number;
  total: number;
  summary: AdminDocumentSummary;
};

/** OpenAPI AdminDocumentDetailResponse. */
export type AdminDocumentDetail = {
  id: string;
  title: string;
  filename: string | null;
  workspace_id: string;
  workspace_name: string;
  file_type: FileType;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  current_version: DocumentVersion | null;
  latest_pipeline_run: PipelineRun | null;
};

export type AdminDocumentSort = "updated_at" | "title" | "size" | "status" | "name";
export type AdminDocumentSortOrder = "asc" | "desc";

export type AdminDocumentListParams = {
  page?: number;
  pageSize?: number;
  workspaceId?: string | null;
  status?: DocumentVersionStatus | null;
  fileType?: FileType | null;
  search?: string | null;
  sort?: AdminDocumentSort;
  order?: AdminDocumentSortOrder;
};
