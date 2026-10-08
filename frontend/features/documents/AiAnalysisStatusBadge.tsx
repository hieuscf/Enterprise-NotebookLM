/**
 * =============================================================================
 * File: AiAnalysisStatusBadge.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Show AI analysis lifecycle separately from document usability.
 * Responsibilities:
 *   - Label NOT ANALYZED / QUEUED / PROCESSING / READY / FAILED / STALE
 * Dependencies:
 *   - lib/utils, types/documents
 * Public Exports:
 *   - AiAnalysisStatusBadge
 * Database/Table: document_versions.ai_analysis_status
 * Related Modules: DocumentStatusIndicator, DocumentDetailView
 * Important Notes: Teal accent only for AI-ready; never mix with citation amber.
 * =============================================================================
 */

import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AiAnalysisStatus } from "@/types/documents";

const LABEL: Record<AiAnalysisStatus, string> = {
  not_analyzed: "Not analyzed",
  queued: "Queued",
  processing: "Analyzing",
  ready: "AI ready",
  failed: "Analysis failed",
  stale: "Stale",
};

type Props = {
  status?: AiAnalysisStatus | null;
  className?: string;
};

export function AiAnalysisStatusBadge({ status, className }: Props) {
  const value: AiAnalysisStatus = status ?? "not_analyzed";
  const busy = value === "queued" || value === "processing";

  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-caption font-medium", className)}
      title={`AI: ${LABEL[value]}`}
    >
      {busy ? (
        <Loader2 className="h-3 w-3 shrink-0 animate-spin text-accent-primary" aria-hidden />
      ) : (
        <span
          aria-hidden
          className={cn(
            "h-1.5 w-1.5 shrink-0 rounded-full",
            value === "ready" && "bg-accent-primary",
            value === "not_analyzed" && "bg-tertiary",
            value === "stale" && "bg-warning",
            value === "failed" && "bg-danger",
          )}
        />
      )}
      <span
        className={cn(
          value === "ready" && "text-accent-primary",
          value === "not_analyzed" && "text-tertiary",
          value === "stale" && "text-warning",
          value === "failed" && "text-danger",
          busy && "text-accent-primary",
        )}
      >
        AI: {LABEL[value]}
      </span>
    </span>
  );
}
