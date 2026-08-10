/**
 * =============================================================================
 * File: ManageUserAccessDialog.tsx
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Dialog to edit workspace roles for a user via existing member PATCH
 *          APIs (Workspace Access Management — not global role management).
 * Responsibilities:
 *   - Show memberships (workspace name + role select)
 *   - Persist role changes with PATCH /workspaces/{id}/members/{userId}
 *   - Surface API errors; keep Cancel/Save accessible
 * Dependencies:
 *   - features/admin/admin-users, lib/api-client.updateWorkspaceMemberRole
 * Public Exports:
 *   - ManageUserAccessDialog
 * Database/Table: workspace_members, roles
 * Related Modules: features/admin/AdminUsersView
 * Important Notes: Only memberships already loaded for admin-eligible
 *   workspaces are editable here — backend still enforces require_workspace_admin.
 * =============================================================================
 */

"use client";

import { Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { ROLE_LABEL_EN } from "@/features/admin/admin-users";
import type { AdminUserMembership, AdminUserRow } from "@/hooks/useAdminUsers";
import { ApiClientError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { WorkspaceRole } from "@/types/auth";

type Props = {
  open: boolean;
  user: AdminUserRow | null;
  submitting: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (changes: { workspaceId: string; role: WorkspaceRole }[]) => void;
};

const ROLE_OPTIONS: WorkspaceRole[] = ["admin", "editor", "viewer"];

export function ManageUserAccessDialog({
  open,
  user,
  submitting,
  error,
  onClose,
  onSubmit,
}: Props) {
  const [draft, setDraft] = useState<Record<string, WorkspaceRole>>({});

  useEffect(() => {
    if (!open || !user) return;
    const next: Record<string, WorkspaceRole> = {};
    for (const m of user.memberships) {
      next[m.workspace_id] = m.role;
    }
    setDraft(next);
  }, [open, user]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, submitting, onClose]);

  if (!open || !user) return null;

  function roleChanges(): { workspaceId: string; role: WorkspaceRole }[] {
    if (!user) return [];
    const changes: { workspaceId: string; role: WorkspaceRole }[] = [];
    for (const m of user.memberships) {
      const next = draft[m.workspace_id];
      if (next && next !== m.role) {
        changes.push({ workspaceId: m.workspace_id, role: next });
      }
    }
    return changes;
  }

  const changes = roleChanges();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="manage-access-title"
        className="flex w-full max-w-lg flex-col rounded-lg border border-border-default bg-surface shadow-lg"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border-default px-5 py-4">
          <div className="min-w-0">
            <h2 id="manage-access-title" className="text-h3 text-primary">
              Manage access
            </h2>
            <p className="mt-0.5 truncate text-body-sm text-secondary">{user.email}</p>
          </div>
          <button
            type="button"
            aria-label="Close"
            disabled={submitting}
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-tertiary hover:bg-elevated disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div className="flex flex-col gap-3 px-5 py-4">
          <p className="text-caption font-semibold uppercase tracking-wide text-tertiary">
            Workspace access
          </p>
          <ul className="flex flex-col gap-2">
            {user.memberships.map((m: AdminUserMembership) => (
              <li
                key={m.workspace_id}
                className="flex flex-col gap-1.5 rounded-md border border-border-default px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <span className="min-w-0 truncate text-body-sm font-medium text-primary">
                  {m.workspace_name}
                </span>
                <label className="flex shrink-0 items-center gap-2 text-body-sm text-secondary">
                  <span className="sr-only">Role for {m.workspace_name}</span>
                  <select
                    value={draft[m.workspace_id] ?? m.role}
                    disabled={submitting}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        [m.workspace_id]: e.target.value as WorkspaceRole,
                      }))
                    }
                    className={cn(
                      "h-9 min-w-[8.5rem] cursor-pointer rounded-md border border-border-default bg-base px-2.5",
                      "text-body-sm text-primary outline-none",
                      "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
                      "disabled:cursor-not-allowed disabled:opacity-60",
                    )}
                  >
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role} value={role}>
                        {ROLE_LABEL_EN[role]}
                      </option>
                    ))}
                  </select>
                </label>
              </li>
            ))}
          </ul>

          {error ? (
            <p role="alert" className="text-body-sm text-danger">
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-border-default px-5 py-3">
          <button
            type="button"
            disabled={submitting}
            onClick={onClose}
            className="inline-flex h-9 items-center rounded-md border border-border-default px-3 text-body-sm font-medium text-secondary hover:bg-elevated disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={submitting || changes.length === 0}
            onClick={() => onSubmit(changes)}
            className={cn(
              "inline-flex h-9 items-center gap-2 rounded-md bg-accent-primary px-3",
              "text-body-sm font-medium text-white hover:bg-accent-primary-hover",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
            Save changes
          </button>
        </div>
      </div>
    </div>
  );
}

/** Map member PATCH errors to a short UI message (shared with the view). */
export function mapAccessUpdateError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    if (err.status === 401) return "Your session has expired. Please sign in again.";
    if (err.status === 403) {
      return "You do not have permission for this action (workspace admin required).";
    }
    if (err.code === "last_admin") {
      return "Cannot change role: this is the last admin of the workspace.";
    }
    if (err.status === 404) return "Member or workspace not found.";
    return err.message || fallback;
  }
  return fallback;
}
