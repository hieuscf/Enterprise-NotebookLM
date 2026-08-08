/**
 * =============================================================================
 * File: ComparisonResult.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Render Comparison result as two columns (similarities | differences).
 * Responsibilities:
 *   - Show processing / failed / empty / completed bullet lists
 * Dependencies:
 *   - comparison-format helpers, types/comparisons
 * Public Exports:
 *   - ComparisonResultView (named to avoid clashing with result type)
 * Database/Table: N/A
 * Related Modules: ComparisonsView
 * Important Notes: Binds to OpenAPI Comparison.result.similarities/differences.
 * =============================================================================
 */

"use client";

import { AlertCircle, Loader2 } from "lucide-react";

import {
  formatComparisonDateTime,
  normalizeComparisonResult,
  statusLabel,
} from "@/features/comparisons/comparison-format";
import { cn } from "@/lib/utils";
import type { Comparison } from "@/types/comparisons";

type Props = {
  comparison: Comparison | null;
  documentTitles?: Record<string, string>;
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

export function ComparisonResultView({
  comparison,
  documentTitles = {},
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
  const { similarities, differences } = normalizeComparisonResult(
    comparison.result,
  );

  return (
    <section
      aria-labelledby="comparison-result-heading"
      className="flex flex-col gap-4 rounded-lg border border-border-default bg-surface p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="comparison-result-heading" className="text-h3 text-primary">
            Kết quả so sánh
          </h2>
          <p className="mt-1 text-body-sm text-secondary">
            {titles.join(" · ")}
          </p>
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

      {comparison.status === "processing" ? (
        <div
          role="status"
          className="flex items-center gap-2 rounded-md border border-warning/30 bg-warning/5 px-3 py-3 text-body-sm text-secondary"
        >
          <Loader2 className="h-4 w-4 animate-spin text-warning" aria-hidden />
          Đang so sánh tài liệu… Kết quả sẽ cập nhật khi hoàn tất.
        </div>
      ) : null}

      {comparison.status === "failed" ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-soft px-3 py-3 text-body-sm text-danger"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          So sánh thất bại. Bạn có thể chọn lại tài liệu và thử lại.
        </div>
      ) : null}

      {comparison.status === "completed" ? (
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
      ) : null}
    </section>
  );
}

/** Alias matching the prompt name ComparisonResult. */
export { ComparisonResultView as ComparisonResult };
