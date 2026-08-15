/**
 * =============================================================================
 * File: ComparisonResult.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Render Comparison result: FR8 columns and CMP-17 clause summary.
 * Responsibilities:
 *   - Show processing / failed / empty / completed states
 *   - Delegate clause-level report to ComparisonSummaryView when present
 * Dependencies:
 *   - comparison-format, comparison-summary, ComparisonSummaryView
 * Public Exports:
 *   - ComparisonResultView (named to avoid clashing with result type)
 * Database/Table: N/A
 * Related Modules: ComparisonsView
 * Important Notes: Clause report is optional; never invent ADDED/REMOVED locally.
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";

import {
  formatComparisonDateTime,
  normalizeComparisonResult,
  statusLabel,
} from "@/features/comparisons/comparison-format";
import { LOADING_STEPS } from "@/features/comparisons/comparison-summary";
import { ComparisonSummaryView } from "@/features/comparisons/ComparisonSummaryView";
import { cn } from "@/lib/utils";
import type { Comparison, DocumentMeta } from "@/types/comparisons";

type Props = {
  workspaceId: string;
  comparison: Comparison | null;
  documentTitles?: Record<string, string>;
  documentMeta?: Record<string, DocumentMeta>;
  initialClauseId?: string | null;
  onClauseChange?: (clauseId: string | null) => void;
  onRetry?: () => void;
};

function BulletColumn({
  title,
  items,
  emptyLabel,
  tone,
}: {
  title: string;
  items: string[];
  emptyLabel: string;
  tone: "same" | "diff";
}) {
  return (
    <div
      className={cn(
        "flex min-h-[12rem] flex-col rounded-lg border p-4",
        tone === "same"
          ? "border-success/25 bg-success/5"
          : "border-warning/25 bg-warning/5",
      )}
    >
      <h3 className="text-body-sm font-semibold text-primary">{title}</h3>
      {items.length === 0 ? (
        <p className="mt-3 text-body-sm text-tertiary">{emptyLabel}</p>
      ) : (
        <ul className="mt-3 flex list-disc flex-col gap-2 pl-5 text-body-sm text-secondary">
          {items.map((item, index) => (
            <li key={`${index}-${item.slice(0, 24)}`}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProcessingState() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-md border border-warning/30 bg-warning/5 px-4 py-4"
    >
      <div className="flex items-center gap-2 text-body-sm font-medium text-primary">
        <Loader2 className="h-4 w-4 animate-spin text-warning" aria-hidden />
        Đang so sánh tài liệu…
      </div>
      <ol className="mt-3 flex flex-col gap-1.5 text-body-sm text-secondary">
        {LOADING_STEPS.map((step) => (
          <li key={step} className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-warning/70" aria-hidden />
            {step}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-caption text-tertiary">
        Kết quả sẽ cập nhật khi hoàn tất. Không hiển thị phần trăm giả lập.
      </p>
    </div>
  );
}

export function ComparisonResultView({
  workspaceId,
  comparison,
  documentTitles = {},
  documentMeta = {},
  initialClauseId = null,
  onClauseChange,
  onRetry,
}: Props) {
  if (!comparison) {
    return (
      <section
        aria-label="Kết quả so sánh"
        className="rounded-lg border border-dashed border-border-default bg-surface/60 px-4 py-10 text-center"
      >
        <p className="text-body-sm text-tertiary">
          Chọn tài liệu và nhấn So sánh, hoặc mở một mục trong lịch sử để xem kết quả.
        </p>
      </section>
    );
  }

  const titles = comparison.document_ids.map(
    (id) => documentTitles[id] ?? id.slice(0, 8),
  );
  const { similarities, differences, contract_comparison } =
    normalizeComparisonResult(comparison.result);

  return (
    <section
      aria-labelledby="comparison-result-heading"
      className="flex flex-col gap-4 rounded-lg border border-border-default bg-surface p-4 sm:p-5"
    >
      {comparison.status !== "completed" || !contract_comparison ? (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="comparison-result-heading" className="text-h3 text-primary">
              Kết quả so sánh
            </h2>
            <p className="mt-1 text-body-sm text-secondary">{titles.join(" · ")}</p>
            <p className="mt-0.5 text-caption text-tertiary">
              {formatComparisonDateTime(comparison.created_at)}
            </p>
          </div>
          <span
            className={cn(
              "rounded-full px-2.5 py-1 text-caption font-semibold",
              comparison.status === "completed" && "bg-success/10 text-success",
              comparison.status === "processing" && "bg-warning/10 text-warning",
              comparison.status === "failed" && "bg-danger-soft text-danger",
            )}
          >
            {statusLabel(comparison.status)}
          </span>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-3">
        <Link
          href={`/workspaces/${workspaceId}/documents`}
          className="inline-flex items-center gap-1.5 text-caption text-secondary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          Quay lại tài liệu
        </Link>
      </div>

      {comparison.status === "processing" ? <ProcessingState /> : null}

      {comparison.status === "failed" ? (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-md border border-danger/30 bg-danger-soft px-3 py-3 text-body-sm text-danger"
        >
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div>
              <p className="font-medium">Không hoàn tất được so sánh.</p>
              <p className="mt-1 text-secondary">
                Bạn có thể chọn lại tài liệu và thử lại. Chi tiết kỹ thuật không được hiển thị.
              </p>
            </div>
          </div>
          {onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex h-9 w-fit items-center rounded-md border border-danger/30 bg-surface px-3 text-caption font-medium text-primary hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
            >
              Thử lại
            </button>
          ) : null}
        </div>
      ) : null}

      {comparison.status === "completed" && contract_comparison ? (
        <ComparisonSummaryView
          workspaceId={workspaceId}
          comparison={comparison}
          report={contract_comparison}
          documentMeta={documentMeta}
          initialClauseId={initialClauseId}
          onClauseChange={onClauseChange}
        />
      ) : null}

      {comparison.status === "completed" && !contract_comparison ? (
        <div className="flex flex-col gap-4">
          <p
            role="status"
            className="rounded-md border border-border-default bg-elevated px-3 py-2 text-body-sm text-secondary"
          >
            Báo cáo điều khoản chưa có cho so sánh này. Đang hiển thị tóm tắt AI từ ngữ cảnh tài liệu.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <BulletColumn
              title="Điểm giống nhau"
              items={similarities}
              emptyLabel="Không có điểm giống nhau được nêu trong ngữ cảnh."
              tone="same"
            />
            <BulletColumn
              title="Điểm khác nhau"
              items={differences}
              emptyLabel="Không có điểm khác nhau được nêu trong ngữ cảnh."
              tone="diff"
            />
          </div>
        </div>
      ) : null}

      {comparison.status === "completed" && contract_comparison && (similarities.length > 0 || differences.length > 0) ? (
        <details className="rounded-md border border-border-default bg-elevated/40 px-3 py-2">
          <summary className="cursor-pointer text-body-sm font-medium text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40">
            Tóm tắt AI (ngữ cảnh tài liệu)
          </summary>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <BulletColumn
              title="Điểm giống nhau"
              items={similarities}
              emptyLabel="Không có điểm giống nhau được nêu trong ngữ cảnh."
              tone="same"
            />
            <BulletColumn
              title="Điểm khác nhau"
              items={differences}
              emptyLabel="Không có điểm khác nhau được nêu trong ngữ cảnh."
              tone="diff"
            />
          </div>
        </details>
      ) : null}
    </section>
  );
}

/** Alias matching the prompt name ComparisonResult. */
export { ComparisonResultView as ComparisonResult };
