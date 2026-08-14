/**
 * =============================================================================
 * File: VersionHistoryDrawer.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Side drawer wrapping DocumentVersionHistory for the reader chrome.
 * Responsibilities:
 *   - Present version list without burying the document canvas
 * Dependencies:
 *   - DocumentVersionHistory, lucide-react
 * Public Exports:
 *   - VersionHistoryDrawer
 * Database/Table: document_versions
 * Related Modules: DocumentDetailView
 * Important Notes: Does not permanently delete historical versions.
 * =============================================================================
 */

"use client";

import { X } from "lucide-react";
import { useEffect, useId } from "react";

import { DocumentVersionHistory } from "@/features/documents/DocumentVersionHistory";
import type { DocumentVersion } from "@/types/documents";

type Props = {
  open: boolean;
  onClose: () => void;
  workspaceId: string;
  documentId: string;
  versions: DocumentVersion[];
  loading: boolean;
  error: string | null;
  onReload: () => void;
  pushSuccess: (message: string) => void;
  pushError: (message: string) => void;
};

export function VersionHistoryDrawer({
  open,
  onClose,
  workspaceId,
  documentId,
  versions,
  loading,
  error,
  onReload,
  pushSuccess,
  pushError,
}: Props) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button
        type="button"
        aria-label="Close version history"
        className="absolute inset-0 bg-primary/30"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-border-default bg-surface shadow-lg"
      >
        <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
          <h2 id={titleId} className="text-h3 text-primary">
            Version history
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-tertiary hover:bg-elevated hover:text-primary"
            aria-label="Close"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <DocumentVersionHistory
            workspaceId={workspaceId}
            documentId={documentId}
            versions={versions}
            loading={loading}
            error={error}
            onReload={onReload}
            pushSuccess={pushSuccess}
            pushError={pushError}
          />
        </div>
      </aside>
    </div>
  );
}
