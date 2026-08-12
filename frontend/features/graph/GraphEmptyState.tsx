/**
 * =============================================================================
 * File: GraphEmptyState.tsx
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Calm empty / loading / error states for the Knowledge Graph page.
 * Responsibilities:
 *   - Empty workspace CTA, progressive loading copy, retryable error
 * Dependencies:
 *   - next/link, lucide-react
 * Public Exports:
 *   - GraphEmptyState, GraphLoadingState, GraphErrorState
 * Database/Table: N/A
 * Related Modules: features/graph/KnowledgeGraphView.tsx
 * Important Notes: Avoid full-screen spinners; prefer editorial messaging.
 * =============================================================================
 */

"use client";

import { AlertCircle, Network, UploadCloud } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export function GraphLoadingState({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex h-full min-h-[320px] flex-col items-center justify-center gap-4 px-6 text-center",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex gap-1.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-8 animate-pulse rounded-full bg-accent-secondary/25"
            style={{ animationDelay: `${i * 160}ms` }}
          />
        ))}
      </div>
      <div>
        <p className="text-h3 text-primary">Đang xây dựng đồ thị tri thức…</p>
        <ul className="mt-3 space-y-1 text-body-sm text-secondary">
          <li>Phân tích thực thể</li>
          <li>Ánh xạ quan hệ</li>
          <li>Tổ chức chủ đề</li>
        </ul>
      </div>
    </div>
  );
}

export function GraphEmptyState({
  workspaceId,
  className,
}: {
  workspaceId: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full min-h-[320px] flex-col items-center justify-center px-6 text-center",
        className,
      )}
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-md bg-accent-secondary-soft">
        <Network className="h-5 w-5 text-accent-secondary" aria-hidden />
      </span>
      <h2 className="mt-4 text-h2 text-primary">Chưa có đồ thị tri thức</h2>
      <p className="mt-2 max-w-sm text-body-sm text-secondary">
        Tải tài liệu lên để xây dựng đồ thị tri thức cho workspace này.
      </p>
      <Link
        href={`/workspaces/${workspaceId}/upload`}
        className="mt-5 inline-flex cursor-pointer items-center gap-2 rounded-md bg-accent-primary px-4 py-2 text-body-sm font-medium text-white transition-colors hover:bg-accent-primary-hover"
      >
        <UploadCloud className="h-4 w-4" aria-hidden />
        Tải lên tài liệu
      </Link>
    </div>
  );
}

export function GraphErrorState({
  message,
  onRetry,
  className,
}: {
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full min-h-[320px] flex-col items-center justify-center px-6 text-center",
        className,
      )}
      role="alert"
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-md bg-danger-soft">
        <AlertCircle className="h-5 w-5 text-danger" aria-hidden />
      </span>
      <h2 className="mt-4 text-h2 text-primary">
        Không thể tải đồ thị tri thức.
      </h2>
      <p className="mt-2 max-w-sm text-body-sm text-secondary">
        {message?.trim() || "Vui lòng thử lại."}
      </p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 cursor-pointer rounded-md border border-border-default bg-surface px-4 py-2 text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary"
        >
          Thử lại
        </button>
      ) : null}
    </div>
  );
}
