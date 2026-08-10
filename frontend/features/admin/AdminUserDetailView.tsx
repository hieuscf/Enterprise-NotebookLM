/**
 * =============================================================================
 * File: AdminUserDetailView.tsx
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Thin skeleton for `/admin/users/[userId]` so list navigation does
 *          not 404. Full Identity / Activity console is out of scope for the
 *          list-page task — this view loads memberships from the same
 *          admin-eligible aggregation used by the list.
 * Responsibilities:
 *   - Resolve user from aggregated admin members (no GET /users/{id})
 *   - Show email + workspace memberships with roles
 *   - Deep-link to `/admin/workspaces/{id}`
 * Dependencies:
 *   - features/admin/AdminShell, AdminCard, admin-users; hooks/useAuth, useAdminUsers
 * Public Exports:
 *   - AdminUserDetailView
 * Database/Table: workspace_members
 * Related Modules: app/admin/users/[userId]/page.tsx
 * Important Notes: If the user is not a member of any admin-eligible workspace,
 *   they are outside the caller's visibility scope (shown as not found).
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import {
  initialsFromEmail,
  ROLE_BADGE_CLASS,
  ROLE_LABEL_EN,
} from "@/features/admin/admin-users";
import { formatDateTimeShort } from "@/features/admin/admin-format";
import { AdminCard } from "@/features/admin/AdminCard";
import { AdminShell } from "@/features/admin/AdminShell";
import { useAdminUsers } from "@/hooks/useAdminUsers";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

type Props = {
  userId: string;
};

export function AdminUserDetailView({ userId }: Props) {
  const { user: authUser } = useAuth();
  const { users, loading, error, reloadMembers, isSystemAdmin } = useAdminUsers();

  const target = useMemo(
    () => users.find((u) => u.user_id === userId) ?? null,
    [users, userId],
  );

  return (
    <AdminShell active="users" user={authUser}>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <Link
          href="/admin/users"
          className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium text-secondary hover:text-accent-primary"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to Users
        </Link>

        {loading ? (
          <div className="flex items-center gap-2 rounded-lg border border-border-default bg-surface px-4 py-10 text-body-sm text-tertiary">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Loading user…
          </div>
        ) : error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="flex flex-col gap-2">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => void reloadMembers()}
                className="w-fit text-body-sm font-medium underline"
              >
                Retry
              </button>
            </div>
          </div>
        ) : !isSystemAdmin ? (
          <div className="rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
            <h1 className="text-h2 text-primary">You don&apos;t have permission to view user management.</h1>
          </div>
        ) : !target ? (
          <div className="rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
            <h1 className="text-h2 text-primary">User not found</h1>
            <p className="mt-2 text-body-sm text-secondary">
              This user is not a member of any workspace you administer, or the id is invalid.
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-start gap-3">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent-tertiary-soft text-body-sm font-semibold text-accent-tertiary">
                {initialsFromEmail(target.email)}
              </span>
              <div className="min-w-0">
                <p className="text-caption font-medium text-accent-primary">FR12 · User profile</p>
                <h1 className="mt-1 truncate text-h1 text-primary">
                  {target.full_name || target.email}
                </h1>
                <p className="mt-1 truncate text-body-sm text-secondary">{target.email}</p>
                <p className="mt-1 text-body-sm text-secondary">
                  Workspace memberships and roles (admin-visible scope).
                </p>
              </div>
            </div>

            <AdminCard
              headingId="admin-user-memberships"
              title="Workspace memberships"
              description="Roles are workspace-scoped. Activity history is not available in the current API contract."
            >
              {target.memberships.length === 0 ? (
                <p className="text-body-sm text-secondary">
                  This account has no workspace memberships yet.
                </p>
              ) : (
              <ul className="flex flex-col gap-2">
                {target.memberships.map((m) => (
                  <li
                    key={m.workspace_id}
                    className="flex flex-col gap-2 rounded-md border border-border-default px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <Link
                        href={`/admin/workspaces/${m.workspace_id}`}
                        className="font-medium text-primary hover:text-accent-primary"
                      >
                        {m.workspace_name}
                      </Link>
                      <p className="text-caption text-tertiary">
                        Joined {formatDateTimeShort(m.joined_at)}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "inline-flex w-fit rounded-full px-2.5 py-0.5 text-caption font-medium",
                        ROLE_BADGE_CLASS[m.role],
                      )}
                    >
                      {ROLE_LABEL_EN[m.role]}
                    </span>
                  </li>
                ))}
              </ul>
              )}
            </AdminCard>
          </>
        )}
      </div>
    </AdminShell>
  );
}
