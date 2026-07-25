/**
 * =============================================================================
 * File: page.tsx (/)
 * Module/Service: Web App
 * Layer: UI
 * Purpose: Protected home — session summary + link into Workspace Management.
 * Responsibilities:
 *   - Show signed-in user from /auth/me
 *   - Point users to /workspaces (FR1 UI)
 * Dependencies:
 *   - hooks/useAuth, features/shell/AppShell
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts (requires auth cookie), app/workspaces
 * Important Notes: Demo RBAC delete button removed — real UI lives under /workspaces.
 * =============================================================================
 */

"use client";

import { ArrowRight, FolderKanban } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";

export default function HomePage() {
  const { user, loading } = useAuth();

  return (
    <AppShell active="home" user={user}>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <section className="rounded-lg border border-border-default bg-surface p-6 shadow-xs">
          <h1 className="text-h1 text-primary">Tổng quan</h1>
          <p className="mt-1 text-body-sm text-secondary">
            Phiên đăng nhập và lối tắt vào quản lý Workspace.
          </p>

          {loading ? (
            <p className="mt-4 text-body-sm text-tertiary">Đang tải…</p>
          ) : user ? (
            <dl className="mt-5 grid gap-3 text-body-sm sm:grid-cols-2">
              <div>
                <dt className="text-tertiary">Họ tên</dt>
                <dd className="text-primary">{user.full_name}</dd>
              </div>
              <div>
                <dt className="text-tertiary">Email</dt>
                <dd className="text-primary">{user.email}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-tertiary">Số Workspace đang tham gia</dt>
                <dd className="text-primary">{user.workspaces.length}</dd>
              </div>
            </dl>
          ) : (
            <p className="mt-4 text-body-sm text-danger">
              Không tải được thông tin người dùng. Hãy{" "}
              <Link href="/login" className="underline">
                đăng nhập lại
              </Link>
              .
            </p>
          )}
        </section>

        <Link
          href="/workspaces"
          className="group flex items-center justify-between gap-4 rounded-lg border border-border-default bg-surface p-6 shadow-xs transition-shadow hover:shadow-md"
        >
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent-primary-soft">
              <FolderKanban className="h-5 w-5 text-accent-primary" aria-hidden />
            </span>
            <div>
              <h2 className="text-h3 text-primary group-hover:text-accent-primary">
                Quản lý Workspaces
              </h2>
              <p className="mt-1 text-body-sm text-secondary">
                Tạo, sửa, xoá workspace và xem chi tiết theo quyền hiện tại.
              </p>
            </div>
          </div>
          <ArrowRight
            className="h-5 w-5 shrink-0 text-tertiary transition-transform group-hover:translate-x-0.5 group-hover:text-accent-primary"
            aria-hidden
          />
        </Link>
      </div>
    </AppShell>
  );
}
