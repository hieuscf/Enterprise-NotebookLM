/**
 * =============================================================================
 * File: DocumentStatusIndicator.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Compact Ready / Processing / Failed status for list + context bar.
 * Responsibilities:
 *   - Dot + short label (not long sentences); accessible text
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - DocumentStatusIndicator
 * Database/Table: document_versions.status
 * Related Modules: DocumentList, DocumentDetailView
 * Important Notes: Do not rely on color alone — includes text label.
 * =============================================================================
 */

import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { DocumentVersionStatus } from "@/types/documents";

const LABEL: Record<DocumentVersionStatus, string> = {
  ready: "Ready",
  processing: "Processing",
  failed: "Processing failed",
};

type Props = {
  status: DocumentVersionStatus;
  className?: string;
  /** Optional stage hint under the label (processing only). */
  hint?: string | null;
};

export function DocumentStatusIndicator({ status, className, hint }: Props) {
  return (
    <span
      className={cn("inline-flex min-w-0 flex-col gap-0.5", className)}
      title={LABEL[status]}
    >
      <span className="inline-flex items-center gap-1.5 text-caption font-medium">
        {status === "processing" ? (
          <Loader2
            className="h-3 w-3 shrink-0 animate-spin text-warning"
            aria-hidden
          />
        ) : (
          <span
            aria-hidden
            className={cn(
              "h-1.5 w-1.5 shrink-0 rounded-full",
              status === "ready" && "bg-success",
              status === "failed" && "bg-danger",
            )}
          />
        )}
        <span
          className={cn(
            status === "ready" && "text-success",
            status === "processing" && "text-warning",
            status === "failed" && "text-danger",
          )}
        >
          {LABEL[status]}
        </span>
      </span>
      {hint && status === "processing" ? (
        <span className="pl-3 text-[10px] text-tertiary">{hint}</span>
      ) : null}
    </span>
  );
}
