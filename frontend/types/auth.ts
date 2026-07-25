/**
 * =============================================================================
 * File: auth.ts
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: TypeScript types for AuthToken / User matching OpenAPI (FR12).
 * Responsibilities:
 *   - Align frontend auth types with backend Pydantic schemas
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml
 * Public Exports:
 *   - AuthToken, WorkspaceMembership, User, WorkspaceRole
 * Database/Table: N/A
 * Related Modules: frontend/lib/api-client, hooks/useWorkspaceRole
 * Important Notes: role enum must stay admin | editor | viewer.
 * =============================================================================
 */

export type WorkspaceRole = "admin" | "editor" | "viewer";

export type AuthToken = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer" | string;
  expires_in: number;
};

export type WorkspaceMembership = {
  workspace_id: string;
  role: WorkspaceRole;
};

export type User = {
  id: string;
  email: string;
  full_name: string;
  workspaces: WorkspaceMembership[];
};
