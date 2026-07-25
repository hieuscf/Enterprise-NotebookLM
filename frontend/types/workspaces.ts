/**
 * =============================================================================
 * File: workspaces.ts
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Workspace CRUD matching OpenAPI (FR1).
 * Responsibilities:
 *   - Align frontend Workspace models with backend Pydantic schemas
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml
 * Public Exports:
 *   - Workspace, WorkspaceListResponse, WorkspaceCreateInput, WorkspaceUpdateInput
 *   - WorkspaceMember, AddMemberInput, UpdateMemberRoleInput
 * Database/Table: N/A
 * Related Modules: lib/api-client, features/workspaces
 * Important Notes: deleted_at is not exposed in API responses.
 * =============================================================================
 */

import type { WorkspaceRole } from "./auth";

export type Workspace = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceListResponse = {
  items: Workspace[];
  page: number;
  page_size: number;
  total: number;
};

export type WorkspaceCreateInput = {
  name: string;
  description?: string | null;
};

export type WorkspaceUpdateInput = {
  name?: string;
  description?: string | null;
};

/** Matches OpenAPI WorkspaceMember (GET/POST/PATCH .../members). */
export type WorkspaceMember = {
  user_id: string;
  email: string;
  role: WorkspaceRole;
  joined_at: string;
};

/** POST /workspaces/{id}/members — user_id is required by the API contract
 * (no email-lookup endpoint exists yet; admin must know the target user's UUID). */
export type AddMemberInput = {
  user_id: string;
  role: WorkspaceRole;
};

export type UpdateMemberRoleInput = {
  role: WorkspaceRole;
};
