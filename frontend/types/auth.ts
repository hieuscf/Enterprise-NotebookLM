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
 *   - AuthToken, WorkspaceMembership, User, WorkspaceRole, PlatformRole
 * Database/Table: N/A
 * Related Modules: frontend/lib/api-client, hooks/useWorkspaceRole, lib/rbac
 * Important Notes:
 *   - platform_role is Platform Manage (or null); workspaces[].role is Workspace RBAC.
 *   - Workspace role enum must stay admin | editor | viewer (never manage).
 * =============================================================================
 */

export type WorkspaceRole = "admin" | "editor" | "viewer";

export type PlatformRole = "manage";

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
  /** Platform Manage for /admin/*; null for ordinary users. */
  platform_role: PlatformRole | null;
  workspaces: WorkspaceMembership[];
};
