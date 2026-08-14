/**
 * =============================================================================
 * File: UploadVersionDialog.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Modal to upload a new document version (replace mode).
 * Responsibilities:
 *   - Wrap DocumentUploadDropzone; confirm cancel while idle
 * Dependencies:
 *   - DocumentUploadDropzone, lucide-react
 * Public Exports:
 *   - UploadVersionDialog
 * Database/Table: document_versions
 * Related Modules: DocumentDetailView
 * Important Notes: Creates a new version — does not create a new document.
 * =============================================================================
 */

"use client";

import { X } from "lucide-react";
import { useEffect, useId } from "react";

import { DocumentUploadDropzone } from "@/features/documents/DocumentUploadDropzone";
import type { StagedFile } from "@/hooks/useDocumentUploadQueue";

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (staged: StagedFile[]) => void;
};

export function UploadVersionDialog({ open, onClose, onSubmit }: Props) {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Close dialog"
        className="absolute inset-0 bg-primary/40"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 w-full max-w-lg rounded-lg border border-border-default bg-surface p-6 shadow-lg"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id={titleId} className="text-h3 text-primary">
              Upload new version
            </h2>
            <p className="mt-1 text-body-sm text-secondary">
              Replace the current document with a new version. The existing
              document remains available through version history.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-tertiary hover:bg-elevated hover:text-primary"
            aria-label="Close"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div className="mt-5">
          <DocumentUploadDropzone
            mode="replace"
            onSubmit={(staged) => {
              onSubmit(staged);
              onClose();
            }}
          />
        </div>

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-md border border-border-default px-4 text-body-sm font-medium text-secondary hover:bg-elevated"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
