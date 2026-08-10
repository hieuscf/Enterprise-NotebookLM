/**
 * =============================================================================
 * File: RequireManage.tsx
 * Module/Service: Auth (Web App) — Platform RBAC
 * Layer: UI
 * Purpose: Route guard for /admin/* — Platform Manage only.
 * Responsibilities:
 *   - Wait for /auth/me; redirect unauthenticated via existing middleware
 *   - Show 403 Unauthorized when platform_role !== manage
 * Dependencies:
 *   - hooks/useAuth, lib/rbac.canAccessAdmin
 * Public Exports:
 *   - RequireManage
 * Database/Table: N/A
 * Related Modules: app/admin/layout.tsx
 * Important Notes: Workspace Admin must NOT pass this guard.
 * =============================================================================
 */

"use client";

import { ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

import { useAuth } from "@/hooks/useAuth";
import { canAccessAdmin } from "@/lib/rbac";

type Props = {
  children: ReactNode;
};

export function RequireManage({ children }: Props) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center px-6 py-16 text-body-sm text-secondary">
        Đang kiểm tra quyền truy cập…
      </div>
    );
  }

  if (!canAccessAdmin(user)) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
            <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
          </span>
          <h1 className="text-h2 text-primary">403 — Không có quyền truy cập</h1>
          <p className="max-w-md text-body-sm text-secondary">
            Admin Console chỉ dành cho tài khoản có quyền Platform{" "}
            <strong>Manage</strong>. Vai trò Workspace Admin không cấp quyền truy cập{" "}
            <code className="text-caption">/admin</code>.
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
