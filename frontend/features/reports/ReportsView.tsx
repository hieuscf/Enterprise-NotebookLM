/**
 * =============================================================================
 * File: ReportsView.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Workspace report generation screen (FR9 / UC8).
 * Responsibilities:
 *   - Compose ReportBuilder + ReportList
 *   - Create/poll/download/delete via useReports
 * Dependencies:
 *   - AppShell, useReports, useWorkspaceRole, ConfirmDialog
 * Public Exports:
 *   - ReportsView
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/reports/page.tsx
 * Important Notes: POST is async 202; UI polls until ready|failed.
 * =============================================================================
 */

"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ReportBuilder } from "@/features/reports/ReportBuilder";
import { ReportList } from "@/features/reports/ReportList";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useReports } from "@/hooks/useReports";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import { cn } from "@/lib/utils";
import type { Report } from "@/types/reports";

type Props = {
  workspaceId: string;
};

export function ReportsView({ workspaceId }: Props) {
  const { user } = useAuth();
  const { isEditor, loading: roleLoading } = useWorkspaceRole(workspaceId);
  const {
    reports,
    loading,
    error,
    creating,
    deletingId,
    downloadingId,
    reload,
    create,
    remove,
    download,
    upsertReport,
  } = useReports(workspaceId);

  const [pendingDelete, setPendingDelete] = useState<Report | null>(null);

  async function confirmDelete() {
    if (!pendingDelete) return;
    const ok = await remove(pendingDelete.id);
    if (ok) setPendingDelete(null);
  }

  return (
    <AppShell active="reports" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-accent-primary">
              FR9 · AI Tools
            </p>
            <h1 className="mt-1 text-h1 text-primary">Báo cáo</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Tổng hợp nguồn đã có trong workspace và xuất PDF / DOCX / Markdown.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void reload()}
            disabled={loading}
            className={cn(
              "inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border-default px-3",
              "text-body-sm font-medium text-secondary hover:bg-elevated",
              "disabled:opacity-50",
            )}
          >
            <RefreshCw
              className={cn("h-4 w-4", loading && "animate-spin")}
              aria-hidden
            />
            Làm mới
          </button>
        </div>

        {error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-soft px-3 py-2.5 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}

        <ReportBuilder
          workspaceId={workspaceId}
          canEdit={isEditor && !roleLoading}
          submitting={creating}
          onSubmit={create}
          onDownload={(id) => download(id)}
          onCreated={upsertReport}
        />

        <section
          aria-labelledby="report-list-heading"
          className="rounded-lg border border-border-default bg-surface p-4 sm:p-5"
        >
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 id="report-list-heading" className="text-h3 text-primary">
              Báo cáo đã tạo
            </h2>
            <span className="text-caption text-tertiary">
              {loading ? "…" : `${reports.length} mục`}
            </span>
          </div>
          {loading && reports.length === 0 ? (
            <p className="text-body-sm text-tertiary">Đang tải danh sách…</p>
          ) : (
            <ReportList
              reports={reports}
              canDelete={isEditor && !roleLoading}
              deletingId={deletingId}
              downloadingId={downloadingId}
              onDownload={(row) => void download(row.id)}
              onDelete={(row) => setPendingDelete(row)}
            />
          )}
        </section>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Xoá báo cáo?"
        description="Báo cáo và file xuất liên quan sẽ bị xoá. Thao tác này không thể hoàn tác."
        confirmLabel="Xoá"
        confirming={deletingId !== null}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </AppShell>
  );
}
