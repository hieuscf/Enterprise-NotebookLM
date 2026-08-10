/**
 * =============================================================================
 * File: AdminDocumentsMetrics.tsx
 * Module/Service: Admin Document Management (Web App) — FR2 / FR12
 * Layer: UI
 * Purpose: Compact summary metrics row for `/admin/documents`.
 * Responsibilities:
 *   - Render Total / Processing / Ready / Failed from AdminDocumentSummary
 *   - Optional click → status filter (Ready/Processing/Failed)
 * Dependencies:
 *   - types/admin, lib/utils
 * Public Exports:
 *   - AdminDocumentsMetrics
 * Database/Table: N/A (counts from GET /admin/documents summary)
 * Related Modules: features/admin/AdminDocumentsView
 * Important Notes: No mock numbers — values come from API summary only.
 * =============================================================================
 */

"use client";

import { cn } from "@/lib/utils";
import type { AdminDocumentSummary } from "@/types/admin";
import type { DocumentVersionStatus } from "@/types/documents";

type Props = {
  summary: AdminDocumentSummary;
  loading: boolean;
  activeStatus: DocumentVersionStatus | "";
  onStatusClick: (status: DocumentVersionStatus | "") => void;
};

const METRICS: Array<{
  key: "total" | DocumentVersionStatus;
  label: string;
  status: DocumentVersionStatus | "";
  valueClass: string;
}> = [
  { key: "total", label: "Total Documents", status: "", valueClass: "text-primary" },
  {
    key: "processing",
    label: "Processing",
    status: "processing",
    valueClass: "text-warning",
  },
  { key: "ready", label: "Ready", status: "ready", valueClass: "text-success" },
  { key: "failed", label: "Failed", status: "failed", valueClass: "text-danger" },
];

export function AdminDocumentsMetrics({
  summary,
  loading,
  activeStatus,
  onStatusClick,
}: Props) {
  return (
    <div
      className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border-default bg-border-default sm:grid-cols-4"
      role="group"
      aria-label="Document status summary"
    >
      {METRICS.map((m) => {
        const value = summary[m.key];
        const isActive =
          m.status === "" ? activeStatus === "" : activeStatus === m.status;
        return (
          <button
            key={m.key}
            type="button"
            onClick={() => onStatusClick(isActive && m.status !== "" ? "" : m.status)}
            disabled={loading}
            className={cn(
              "flex flex-col gap-1 bg-surface px-4 py-3 text-left transition-colors",
              "hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-primary/30",
              isActive && m.status !== "" && "bg-elevated",
              loading && "opacity-70",
            )}
            aria-pressed={isActive}
            aria-label={`${m.label}: ${loading ? "loading" : value.toLocaleString("en-US")}`}
          >
            <span className="text-caption font-medium uppercase tracking-wider text-tertiary">
              {m.label}
            </span>
            {loading ? (
              <span className="h-7 w-16 animate-pulse rounded bg-elevated" aria-hidden />
            ) : (
              <span className={cn("text-h2 tabular-nums", m.valueClass)}>
                {value.toLocaleString("en-US")}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
