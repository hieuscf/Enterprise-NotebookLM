/**
 * =============================================================================
 * File: rbac.ts
 * Module/Service: Auth (Web App) — Platform + Workspace RBAC (FR12)
 * Layer: UI
 * Purpose: Central permission helpers separating Platform Manage from Workspace roles.
 * Responsibilities:
 *   - canAccessAdmin — platformRole === "manage"
 *   - Workspace helpers for members / edit / upload (workspace-scoped)
 * Dependencies:
 *   - types/auth
 * Public Exports:
 *   - canAccessAdmin, getWorkspaceRole, canManageMembers, canEditWorkspace,
 *     canUploadDocuments, canDeleteDocuments
 * Database/Table: N/A
 * Related Modules: hooks/useAuth, features/admin/*, features/shell/Sidebar
 * Important Notes:
 *   - admin (workspace) ≠ manage (platform). Never map admin → canAccessAdmin.
 * =============================================================================
 */

import type { User, WorkspaceRole } from "@/types/auth";

export function canAccessAdmin(user: User | null | undefined): boolean {
  return user?.platform_role === "manage";
}

export function getWorkspaceRole(
  user: User | null | undefined,
  workspaceId: string | null | undefined,
): WorkspaceRole | null {
  if (!user || !workspaceId) return null;
  const membership = user.workspaces.find((w) => w.workspace_id === workspaceId);
  return membership?.role ?? null;
}

export function canManageMembers(
  user: User | null | undefined,
  workspaceId: string | null | undefined,
): boolean {
  return getWorkspaceRole(user, workspaceId) === "admin";
}

export function canEditWorkspace(
  user: User | null | undefined,
  workspaceId: string | null | undefined,
): boolean {
  // Platform Manage may edit any workspace from Admin Console; Workspace Admin of that WS too.
  if (canAccessAdmin(user)) return true;
  return getWorkspaceRole(user, workspaceId) === "admin";
}

export function canUploadDocuments(
  user: User | null | undefined,
  workspaceId: string | null | undefined,
): boolean {
  const role = getWorkspaceRole(user, workspaceId);
  return role === "admin" || role === "editor";
}

export function canDeleteDocuments(
  user: User | null | undefined,
  workspaceId: string | null | undefined,
): boolean {
  return getWorkspaceRole(user, workspaceId) === "admin";
}
