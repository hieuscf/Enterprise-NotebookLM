/**
 * =============================================================================
 * File: ExtractionsView.tsx
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Workspace-level Extractions page — pick a document then run/view
 *          information extraction (FR7), separate from document detail.
 * Responsibilities:
 *   - Document picker (useDocuments)
 *   - Host ExtractionSection for the selected document
 * Dependencies:
 *   - AppShell, ExtractionSection, useDocuments, useWorkspaceRole, useToasts
 * Public Exports:
 *   - ExtractionsView
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/extractions/page.tsx
 * Important Notes: Backend APIs remain document-scoped; this page only
 *   changes the UI entry point (sidebar AI Tools → Trích xuất).
 * =============================================================================
 */

"use client";

import { AlertCircle, FileText } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ToastStack } from "@/components/ui/toast";
import { ExtractionSection } from "@/features/extractions/ExtractionSection";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useDocuments } from "@/hooks/useDocuments";
import { useToasts } from "@/hooks/useToasts";
import { useWorkspaceRole } from "@/hooks/useWorkspaceRole";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  /** Optional deep-link: /extractions?documentId=… */
  initialDocumentId?: string | null;
};

export function ExtractionsView({ workspaceId, initialDocumentId = null }: Props) {
  const { user } = useAuth();
  const { isEditor, loading: roleLoading } = useWorkspaceRole(workspaceId);
  const { toasts, pushSuccess, pushError, dismiss } = useToasts();
  const { items: documents, loading: docsLoading, error: docsError } = useDocuments(
    workspaceId,
    { page: 1, pageSize: 100, fileType: null },
  );

  const [documentId, setDocumentId] = useState<string | null>(initialDocumentId);

  useEffect(() => {
    if (initialDocumentId) {
      setDocumentId(initialDocumentId);
      return;
    }
    if (!documentId && documents.length > 0) {
      setDocumentId(documents[0].id);
    }
  }, [initialDocumentId, documents, documentId]);

  const selected = useMemo(
    () => documents.find((d) => d.id === documentId) ?? null,
    [documents, documentId],
  );

  return (
    <AppShell active="extractions" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <div>
          <p className="text-caption font-medium text-accent-primary">FR7 · AI Tools</p>
          <h1 className="mt-1 text-h1 text-primary">Trích xuất thông tin</h1>
          <p className="mt-1 text-body-sm text-secondary">
            Chọn tài liệu trong workspace để trích xuất bảng biểu, sự kiện, hoặc cấu
            trúc JSON.
          </p>
        </div>

        <section
          aria-label="Chọn tài liệu"
          className="rounded-lg border border-border-default bg-surface p-4 sm:p-5"
        >
          <label
            htmlFor="extraction-document-select"
            className="block text-caption font-semibold uppercase tracking-wide text-tertiary"
          >
            Tài liệu
          </label>
          {docsError ? (
            <p
              role="alert"
              className="mt-2 flex items-center gap-2 text-body-sm text-danger"
            >
              <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
              {docsError}
            </p>
          ) : (
            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative min-w-0 flex-1">
                <FileText
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
                  aria-hidden
                />
                <select
                  id="extraction-document-select"
                  value={documentId ?? ""}
                  disabled={docsLoading || documents.length === 0}
                  onChange={(e) => setDocumentId(e.target.value || null)}
                  className={cn(
                    "h-10 w-full appearance-none rounded-md border border-border-default bg-surface pl-9 pr-8",
                    "text-body-sm text-primary focus:border-accent-primary focus:outline-none focus:ring-2 focus:ring-accent-primary/20",
                    "disabled:cursor-not-allowed disabled:opacity-60",
                  )}
                >
                  {documents.length === 0 ? (
                    <option value="">
                      {docsLoading ? "Đang tải tài liệu…" : "Chưa có tài liệu"}
                    </option>
                  ) : (
                    documents.map((doc) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.title}
                      </option>
                    ))
                  )}
                </select>
              </div>
              {selected ? (
                <Link
                  href={`/workspaces/${workspaceId}/documents/${selected.id}`}
                  className="shrink-0 text-body-sm font-medium text-accent-primary hover:underline"
                >
                  Mở tài liệu
                </Link>
              ) : null}
            </div>
          )}
        </section>

        {selected ? (
          <ExtractionSection
            workspaceId={workspaceId}
            documentId={selected.id}
            currentVersionId={selected.current_version_id}
            canEdit={isEditor && !roleLoading}
            onCopied={() => pushSuccess("Đã sao chép kết quả trích xuất.")}
            onCopyFailed={() => pushError("Không sao chép được kết quả trích xuất.")}
            onExportError={(message) => pushError(message)}
            onCreateError={(message) => pushError(message)}
          />
        ) : !docsLoading && documents.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border-default px-4 py-8 text-center text-body-sm text-secondary">
            Workspace chưa có tài liệu.{" "}
            <Link
              href={`/workspaces/${workspaceId}/upload`}
              className="font-medium text-accent-primary hover:underline"
            >
              Tải lên tài liệu
            </Link>{" "}
            để bắt đầu trích xuất.
          </p>
        ) : null}
      </div>

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </AppShell>
  );
}
