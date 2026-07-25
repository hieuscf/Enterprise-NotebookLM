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
 * Database/Table: N/A
 * Related Modules: lib/api-client, features/workspaces
 * Important Notes: deleted_at is not exposed in API responses.
 * =============================================================================
 */

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
