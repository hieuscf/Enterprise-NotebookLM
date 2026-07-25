/**
 * =============================================================================
 * File: useWorkspaceRole.ts
 * Module/Service: Auth / RBAC (Web App)
 * Layer: UI
 * Purpose: Resolve current user's role in a workspace for UI gates (FR12).
 * Responsibilities:
 *   - Read memberships from /auth/me (via useAuth)
 *   - Expose role + helpers (isAdmin, canEdit, …) for hide/disable controls
 * Dependencies:
 *   - hooks/useAuth, types/auth
 * Public Exports:
 *   - useWorkspaceRole
 * Database/Table: N/A
 * Related Modules: Demo Delete Workspace button on home page
 * Important Notes: UI-only gate — backend require_workspace_role remains source of truth.
 * =============================================================================
 */

"use client";

import { useMemo } from "react";

import { useAuth } from "@/hooks/useAuth";
import type { WorkspaceRole } from "@/types/auth";

export function useWorkspaceRole(workspaceId: string | null | undefined) {
  const { user, loading } = useAuth();

  const role: WorkspaceRole | null = useMemo(() => {
    if (!workspaceId || !user) return null;
    const membership = user.workspaces.find(
      (w) => w.workspace_id === workspaceId,
    );
    return membership?.role ?? null;
  }, [user, workspaceId]);

  return {
    role,
    loading,
    isMember: role !== null,
    isAdmin: role === "admin",
    isEditor: role === "editor" || role === "admin",
    isViewer: role === "viewer" || role === "editor" || role === "admin",
  };
}
