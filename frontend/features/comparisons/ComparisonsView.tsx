/**
 * =============================================================================
 * File: ComparisonsView.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Workspace multi-document comparison screen (FR8 / UC7).
 * Responsibilities:
 *   - Compose ComparisonPicker + ComparisonResult + history list
 *   - Create/poll via useComparisons; delete with ConfirmDialog
 * Dependencies:
 *   - AppShell, useComparisons, useDocuments, useWorkspaceRole, ConfirmDialog
 * Public Exports:
 *   - ComparisonsView
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/comparisons/page.tsx
 * Important Notes: POST is async 202; UI polls until completed|failed.
 *   Deep-link: ?comparison=&clause= are identifiers only.
 * =============================================================================
 */

"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { buildComparisonsHref } from "@/features/comparisons/clause-view";
import { ComparisonHistory } from "@/features/comparisons/ComparisonHistory";
import { ComparisonPicker } from "@/features/comparisons/ComparisonPicker";
import { ComparisonResult } from "@/features/comparisons/ComparisonResult";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useComparisons } from "@/hooks/useComparisons";
import { useDocuments } from "@/hooks/useDocuments";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import { cn } from "@/lib/utils";
import type { Comparison } from "@/types/comparisons";

type Props = {
  workspaceId: string;
  initialComparisonId?: string | null;
  initialClauseId?: string | null;
};

export function ComparisonsView({
  workspaceId,
  initialComparisonId = null,
  initialClauseId = null,
}: Props) {
  const router = useRouter();
  const { user } = useAuth();
  const { isEditor, loading: roleLoading } = useWorkspaceRole(workspaceId);
  const {
    comparisons,
    loading,
    error,
    creating,
    deletingId,
    reload,
    create,
    remove,
  } = useComparisons(workspaceId);
  const { items: documents } = useDocuments(workspaceId, {
    page: 1,
    pageSize: 100,
    fileType: null,
  });

  const [selectedId, setSelectedId] = useState<string | null>(
    initialComparisonId,
  );
  const [pendingDelete, setPendingDelete] = useState<Comparison | null>(null);
  const [clauseId, setClauseId] = useState<string | null>(initialClauseId);

  const replaceQuery = useCallback(
    (comparisonId: string | null, nextClauseId: string | null) => {
      router.replace(buildComparisonsHref(workspaceId, comparisonId, nextClauseId), {
        scroll: false,
      });
    },
    [router, workspaceId],
  );

  useEffect(() => {
    if (initialComparisonId) setSelectedId(initialComparisonId);
  }, [initialComparisonId]);

  useEffect(() => {
    setClauseId(initialClauseId);
  }, [initialClauseId]);

  const documentTitles = useMemo(() => {
    const map: Record<string, string> = {};
    for (const doc of documents) {
      map[doc.id] = doc.title;
    }
    return map;
  }, [documents]);

  const documentMeta = useMemo(() => {
    const map: Record<string, { title: string; created_at?: string | null }> = {};
    for (const doc of documents) {
      map[doc.id] = { title: doc.title, created_at: doc.created_at };
    }
    return map;
  }, [documents]);

  const selected = useMemo(
    () => comparisons.find((c) => c.id === selectedId) ?? null,
    [comparisons, selectedId],
  );

  useEffect(() => {
    if (selectedId && !comparisons.some((c) => c.id === selectedId)) {
      setSelectedId(null);
      setClauseId(null);
    }
  }, [comparisons, selectedId]);

  async function handleCompare(documentIds: string[], focus: string) {
    const row = await create(documentIds, focus || null);
    if (row) {
      setSelectedId(row.id);
      setClauseId(null);
      replaceQuery(row.id, null);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    const id = pendingDelete.id;
    const ok = await remove(id);
    if (ok) {
      if (selectedId === id) {
        setSelectedId(null);
        setClauseId(null);
        replaceQuery(null, null);
      }
      setPendingDelete(null);
    }
  }

  return (
    <AppShell active="comparisons" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-accent-primary">
              FR8 · AI Tools
            </p>
            <h1 className="mt-1 text-h1 text-primary">So sánh tài liệu</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Đối chiếu thay đổi giữa các phiên bản hợp đồng và truy vết bằng chứng nguồn.
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

        <div className="grid gap-6 xl:grid-cols-[minmax(18rem,22rem)_minmax(0,1fr)]">
          <div className="flex flex-col gap-6">
            <ComparisonPicker
              workspaceId={workspaceId}
              canEdit={isEditor && !roleLoading}
              submitting={creating}
              onCompare={handleCompare}
            />

            <section
              aria-labelledby="comparison-history-heading"
              className="rounded-lg border border-border-default bg-surface p-4 sm:p-5"
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2
                  id="comparison-history-heading"
                  className="text-h3 text-primary"
                >
                  Lịch sử so sánh
                </h2>
                <span className="text-caption text-tertiary">
                  {loading ? "…" : `${comparisons.length} mục`}
                </span>
              </div>
              {loading && comparisons.length === 0 ? (
                <p className="text-body-sm text-tertiary">Đang tải lịch sử…</p>
              ) : (
                <ComparisonHistory
                  comparisons={comparisons}
                  selectedId={selectedId}
                  canDelete={isEditor && !roleLoading}
                  deletingId={deletingId}
                  documentTitles={documentTitles}
                  onSelect={(row) => {
                    setSelectedId(row.id);
                    setClauseId(null);
                    replaceQuery(row.id, null);
                  }}
                  onDelete={(row) => setPendingDelete(row)}
                />
              )}
            </section>
          </div>

          <ComparisonResult
            workspaceId={workspaceId}
            comparison={selected}
            documentTitles={documentTitles}
            documentMeta={documentMeta}
            initialClauseId={clauseId}
            onClauseChange={(next) => {
              setClauseId(next);
              replaceQuery(selectedId, next);
            }}
            onRetry={
              selected
                ? () => void handleCompare(selected.document_ids, "")
                : undefined
            }
          />
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Xoá so sánh?"
        description="Kết quả so sánh sẽ bị xoá khỏi lịch sử workspace. Thao tác này không thể hoàn tác."
        confirmLabel="Xoá"
        confirming={deletingId !== null}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </AppShell>
  );
}
