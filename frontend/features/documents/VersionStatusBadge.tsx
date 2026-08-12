/**
 * =============================================================================
 * File: VersionStatusBadge.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Shared color/label for document_versions.status across the
 *          document list and version history (FR2 Part 2).
 * Responsibilities:
 *   - ready → green, processing → amber (subtle pulse), failed → red
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - VersionStatusBadge
 * Database/Table: document_versions.status
 * Related Modules: features/documents/DocumentList, DocumentVersionHistory
 * Important Notes: Uses the same success/warning/danger design tokens as the
 *   rest of the app — intentionally amber (not teal) for "processing" so it
 *   doesn't clash with the Part 1 pipeline stepper's "running" accent color.
 * =============================================================================
 */

import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import type { DocumentVersionStatus } from "@/types/documents";

const LABEL: Record<DocumentVersionStatus, string> = {
  ready: "Đã xử lý tài liệu.",
  processing: "Đang xử lý tài liệu...",
  failed: "Không thể xử lý tài liệu. Vui lòng thử lại.",
};

const CLASS: Record<DocumentVersionStatus, string> = {
  ready: "bg-success/10 text-success",
  processing: "bg-warning/10 text-warning",
  failed: "bg-danger-soft text-danger",
};

type Props = {
  status: DocumentVersionStatus;
  className?: string;
};

export function VersionStatusBadge({ status, className }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-caption font-semibold",
        CLASS[status],
        className,
      )}
    >
      {status === "processing" ? (
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
      ) : status === "ready" ? (
        <CheckCircle2 className="h-3 w-3" aria-hidden />
      ) : (
        <XCircle className="h-3 w-3" aria-hidden />
      )}
      {LABEL[status]}
    </span>
  );
}
