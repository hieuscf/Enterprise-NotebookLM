/**
 * =============================================================================
 * File: AdminSectionState.tsx
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Shared skeleton / error+retry / empty-state building blocks so every
 *          Admin Dashboard card handles loading/error/empty the same way and a
 *          single failing section never blanks the rest of the page.
 * Responsibilities:
 *   - SectionSkeleton — animated placeholder bars sized for a card body
 *   - SectionError — friendly message + Retry button (no stack traces/internals)
 *   - SectionEmpty — muted empty-state copy
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - SectionSkeleton, SectionError, SectionEmpty
 * Database/Table: N/A
 * Related Modules: features/admin/*Card.tsx, RecentQueriesTable, RecentPipelineTable
 * Important Notes: Never render raw error.message from the network layer here
 *   beyond the already-sanitized ApiClientError message (backend never leaks
 *   internals in that message per app/schemas/common.py ErrorResponse).
 * =============================================================================
 */

"use client";

import { AlertCircle, RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";

export function SectionSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2.5" role="status" aria-label="Đang tải dữ liệu">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="h-3.5 w-1/3 animate-pulse rounded bg-elevated" />
          <div className="h-3.5 flex-1 animate-pulse rounded bg-elevated" />
        </div>
      ))}
    </div>
  );
}

export function SectionError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-2 rounded-md border border-danger/30 bg-danger-soft px-3 py-3 text-body-sm text-danger"
    >
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>{message}</span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border border-danger/30 px-2.5 py-1",
          "text-caption font-medium text-danger hover:bg-danger/10",
        )}
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden />
        Thử lại
      </button>
    </div>
  );
}

export function SectionEmpty({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-1 py-8 text-center">
      <p className="text-body-sm font-medium text-secondary">{title}</p>
      {description ? (
        <p className="max-w-sm text-caption text-tertiary">{description}</p>
      ) : null}
    </div>
  );
}
