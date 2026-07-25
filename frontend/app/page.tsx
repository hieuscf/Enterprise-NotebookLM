/**
 * =============================================================================
 * File: page.tsx (/)
 * Module/Service: Web App
 * Layer: UI
 * Purpose: Protected home — session summary + RBAC UI demo (Step 4).
 * Responsibilities:
 *   - Show signed-in user from /auth/me
 *   - Demo useWorkspaceRole via Delete Workspace button
 * Dependencies:
 *   - hooks/useAuth, features/auth/DeleteWorkspaceDemoButton
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts (requires auth cookie)
 * Important Notes: Full workspace UI is phase 1.3 — this is auth/RBAC shell only.
 * =============================================================================
 */

"use client";

import Link from "next/link";

import { DeleteWorkspaceDemoButton } from "@/features/auth/DeleteWorkspaceDemoButton";
import { useAuth } from "@/hooks/useAuth";

export default function HomePage() {
  const { user, loading } = useAuth();
  const firstWorkspaceId = user?.workspaces[0]?.workspace_id ?? null;

  return (
    <main className="min-h-screen bg-base">
      <header className="border-b border-border-default bg-surface">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-caption font-medium text-accent-primary">
              NotebookLM Enterprise
            </p>
            <h1 className="text-h2 text-primary">Bảng điều khiển</h1>
          </div>
          <Link
            href="/logout"
            className="rounded-md px-3 py-2 text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary"
          >
            Đăng xuất
          </Link>
        </div>
      </header>

      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <section className="rounded-lg border border-border-default bg-surface p-6 shadow-xs">
          <h2 className="text-h3 text-primary">Phiên đăng nhập</h2>
          {loading ? (
            <p className="mt-3 text-body-sm text-tertiary">Đang tải…</p>
          ) : user ? (
            <dl className="mt-4 grid gap-3 text-body-sm">
              <div>
                <dt className="text-tertiary">Họ tên</dt>
                <dd className="text-primary">{user.full_name}</dd>
              </div>
              <div>
                <dt className="text-tertiary">Email</dt>
                <dd className="text-primary">{user.email}</dd>
              </div>
              <div>
                <dt className="text-tertiary">Workspaces</dt>
                <dd className="text-primary">
                  {user.workspaces.length === 0 ? (
                    <span className="text-secondary">Chưa thuộc workspace nào</span>
                  ) : (
                    <ul className="mt-1 list-inside list-disc text-secondary">
                      {user.workspaces.map((w) => (
                        <li key={w.workspace_id}>
                          <span className="font-mono text-mono text-primary">
                            {w.workspace_id}
                          </span>{" "}
                          — role <span className="text-accent-primary">{w.role}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="mt-3 text-body-sm text-danger">
              Không tải được thông tin người dùng. Hãy{" "}
              <Link href="/login" className="underline">
                đăng nhập lại
              </Link>
              .
            </p>
          )}
        </section>

        <section className="rounded-lg border border-border-default bg-surface p-6 shadow-xs">
          <h2 className="text-h3 text-primary">Demo RBAC UI</h2>
          <p className="mt-2 text-body-sm text-secondary">
            Hook <code className="font-mono text-mono">useWorkspaceRole</code> ẩn
            nút nguy hiểm khi không đủ quyền (admin). Backend vẫn enforce RBAC.
          </p>
          <div className="mt-4">
            {firstWorkspaceId ? (
              <DeleteWorkspaceDemoButton workspaceId={firstWorkspaceId} />
            ) : (
              <p className="text-body-sm text-tertiary">
                Cần ít nhất một workspace membership để demo nút xoá.
              </p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
