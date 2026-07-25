/**
 * =============================================================================
 * File: WorkspaceListView.tsx
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: List page UI — workspaces of current user + create modal (FR1).
 * Responsibilities:
 *   - Render hero header, search filter, grid/list with loading & empty states
 *   - Create workspace then revalidate list + auth memberships
 * Dependencies:
 *   - hooks/useWorkspaces, useAuth; lib/api-client.createWorkspace; features/shell/AppShell
 * Public Exports:
 *   - WorkspaceListView
 * Database/Table: N/A
 * Related Modules: app/workspaces/page.tsx
 * Important Notes: Empty state guides first-workspace creation (no blank page).
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ArrowRight,
  FolderKanban,
  Layers,
  Loader2,
  Plus,
  Search,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { AppShell } from "@/features/shell/AppShell";
import {
  WorkspaceFormModal,
  type WorkspaceFormValues,
} from "@/features/workspaces/WorkspaceFormModal";
import { useAuth } from "@/hooks/useAuth";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { ApiClientError, createWorkspace } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { Workspace } from "@/types/workspaces";

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/** Rotating accent per card so a dense grid stays visually distinguishable. */
const CARD_ACCENTS = [
  { icon: "bg-accent-primary-soft text-accent-primary", ring: "hover:border-accent-primary/40" },
  { icon: "bg-accent-secondary-soft text-accent-secondary", ring: "hover:border-accent-secondary/40" },
  { icon: "bg-accent-tertiary-soft text-accent-tertiary", ring: "hover:border-accent-tertiary/40" },
];

function initialsOf(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  const parts = trimmed.split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("");
}

function WorkspaceCardSkeleton() {
  return (
    <div className="flex h-full flex-col gap-4 rounded-xl border border-border-default bg-surface p-5">
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 shrink-0 animate-pulse rounded-lg bg-elevated" />
        <div className="flex-1 space-y-2 pt-0.5">
          <div className="h-4 w-2/3 animate-pulse rounded bg-elevated" />
          <div className="h-3 w-full animate-pulse rounded bg-elevated" />
        </div>
      </div>
      <div className="mt-auto h-3 w-1/3 animate-pulse rounded bg-elevated" />
    </div>
  );
}

export function WorkspaceListView() {
  const router = useRouter();
  const { user, reload: reloadAuth } = useAuth();
  const { items, total, loading, error, reload } = useWorkspaces();

  const [query, setQuery] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (ws: Workspace) =>
        ws.name.toLowerCase().includes(q) ||
        (ws.description ?? "").toLowerCase().includes(q),
    );
  }, [items, query]);

  async function handleCreate(values: WorkspaceFormValues) {
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await createWorkspace({
        name: values.name,
        description: values.description || null,
      });
      await Promise.all([reload(), reloadAuth()]);
      setCreateOpen(false);
      router.push(`/workspaces/${created.id}`);
    } catch (err) {
      setFormError(
        err instanceof ApiClientError
          ? err.message
          : "Không tạo được workspace. Thử lại sau.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell active="workspaces" user={user}>
      {/* Hero */}
      <div className="relative overflow-hidden border-b border-border-default bg-surface">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(circle at 8% 20%, color-mix(in srgb, var(--accent-primary) 10%, transparent), transparent 45%), radial-gradient(circle at 92% 0%, color-mix(in srgb, var(--accent-tertiary) 12%, transparent), transparent 45%)",
          }}
        />
        <div className="relative mx-auto flex max-w-6xl flex-col gap-6 px-6 py-10 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="inline-flex items-center gap-1.5 rounded-full bg-accent-primary-soft px-3 py-1 text-caption font-medium text-accent-primary">
              <Layers className="h-3.5 w-3.5" aria-hidden />
              FR1 · Workspace Management
            </p>
            <h1 className="mt-3 text-display text-primary">Workspaces</h1>
            <p className="mt-2 max-w-xl text-body text-secondary">
              Không gian làm việc riêng cho từng phòng ban / dự án — tài liệu,
              thành viên và quyền truy cập được tách biệt rõ ràng.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setFormError(null);
              setCreateOpen(true);
            }}
            className={cn(
              "inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-md bg-accent-primary px-5",
              "text-body-sm font-medium text-white shadow-sm",
              "transition-colors hover:bg-accent-primary-hover",
            )}
          >
            <Plus className="h-4 w-4" aria-hidden />
            Tạo Workspace mới
          </button>
        </div>
      </div>

      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
        {!loading && !error && items.length > 0 ? (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-body-sm text-secondary">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-elevated">
                <Users className="h-3.5 w-3.5 text-tertiary" aria-hidden />
              </span>
              Bạn là thành viên của{" "}
              <span className="font-semibold text-primary">{total}</span>{" "}
              workspace{total === 1 ? "" : "s"}
            </div>
            <div className="relative w-full sm:w-72">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
                aria-hidden
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Tìm workspace theo tên hoặc mô tả…"
                className={cn(
                  "h-10 w-full rounded-md border border-border-default bg-surface pl-9 pr-3",
                  "text-body-sm text-primary placeholder:text-tertiary",
                  "outline-none transition-colors",
                  "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
                )}
              />
            </div>
          </div>
        ) : null}

        {loading ? (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <li key={i}>
                <WorkspaceCardSkeleton />
              </li>
            ))}
          </ul>
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
                onClick={() => void reload()}
                className="w-fit text-body-sm font-medium underline"
              >
                Thử lại
              </button>
            </div>
          </div>
        ) : items.length === 0 ? (
          <section className="relative overflow-hidden rounded-xl border border-dashed border-border-strong bg-surface px-6 py-14 text-center shadow-xs">
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0"
              style={{
                backgroundImage:
                  "radial-gradient(circle at 50% 0%, color-mix(in srgb, var(--accent-primary) 6%, transparent), transparent 60%)",
              }}
            />
            <span className="relative mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-accent-primary-soft">
              <FolderKanban className="h-7 w-7 text-accent-primary" aria-hidden />
            </span>
            <h2 className="relative mt-5 text-h2 text-primary">
              Chưa có Workspace nào
            </h2>
            <p className="relative mx-auto mt-2 max-w-md text-body-sm text-secondary">
              Tạo Workspace đầu tiên để bắt đầu quản lý tài liệu, thành viên và
              quyền truy cập theo phòng ban hoặc dự án.
            </p>
            <button
              type="button"
              onClick={() => {
                setFormError(null);
                setCreateOpen(true);
              }}
              className={cn(
                "relative mt-6 inline-flex h-11 items-center gap-2 rounded-md bg-accent-primary px-5",
                "text-body-sm font-medium text-white shadow-sm hover:bg-accent-primary-hover",
              )}
            >
              <Plus className="h-4 w-4" aria-hidden />
              Tạo Workspace đầu tiên
            </button>
          </section>
        ) : filtered.length === 0 ? (
          <div className="rounded-lg border border-border-default bg-surface px-6 py-10 text-center text-body-sm text-secondary">
            Không tìm thấy workspace phù hợp với{" "}
            <span className="font-medium text-primary">&quot;{query}&quot;</span>.
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((ws, index) => {
              const accent = CARD_ACCENTS[index % CARD_ACCENTS.length];
              return (
                <li key={ws.id}>
                  <Link
                    href={`/workspaces/${ws.id}`}
                    className={cn(
                      "group flex h-full flex-col gap-4 rounded-xl border border-border-default bg-surface p-5",
                      "shadow-xs transition-all duration-150 hover:-translate-y-0.5 hover:shadow-md",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
                      accent.ring,
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span
                        className={cn(
                          "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-body-sm font-semibold",
                          accent.icon,
                        )}
                      >
                        {initialsOf(ws.name)}
                      </span>
                      <ArrowRight
                        className="mt-1 h-4 w-4 shrink-0 text-tertiary opacity-0 transition-all group-hover:translate-x-0.5 group-hover:text-accent-primary group-hover:opacity-100"
                        aria-hidden
                      />
                    </div>

                    <div className="min-w-0 flex-1">
                      <h2 className="truncate text-h3 text-primary group-hover:text-accent-primary">
                        {ws.name}
                      </h2>
                      <p className="mt-1.5 line-clamp-2 text-body-sm text-secondary">
                        {ws.description?.trim()
                          ? ws.description
                          : "Chưa có mô tả"}
                      </p>
                    </div>

                    <p className="mt-auto border-t border-border-default pt-3 text-caption text-tertiary">
                      Cập nhật {formatDate(ws.updated_at)}
                    </p>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <WorkspaceFormModal
        open={createOpen}
        mode="create"
        submitting={submitting}
        error={formError}
        onClose={() => {
          if (!submitting) setCreateOpen(false);
        }}
        onSubmit={handleCreate}
      />
    </AppShell>
  );
}
