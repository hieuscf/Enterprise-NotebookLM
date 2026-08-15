/**
 * =============================================================================
 * File: ComparisonReviewActions.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TASK-CMP-20 reviewer actions for a single comparison finding.
 * Responsibilities:
 *   - Record REVIEWED / NEEDS_ATTENTION / ACKNOWLEDGED / OPEN
 *   - Keep system analysis visually separate from the reviewer decision
 * Dependencies:
 *   - comparison-review helpers, comparison-badges, design tokens
 * Public Exports:
 *   - ComparisonReviewActions
 * Database/Table: N/A
 * Related Modules: ComparisonSummaryView, ClauseComparisonView
 * Important Notes: Does not change clause status, risk, evidence, or AI text.
 * =============================================================================
 */

"use client";

import { AlertTriangle, Check, Eye, Loader2, RotateCcw } from "lucide-react";

import { ReviewBadge } from "@/features/comparisons/comparison-badges";
import {
  formatReviewerLine,
  reviewDecision,
  reviewState,
  type ReviewMap,
} from "@/features/comparisons/comparison-review";
import { cn } from "@/lib/utils";
import type { ComparisonReviewStatus } from "@/types/comparisons";

type Props = {
  clauseId: string;
  review: ReviewMap | null | undefined;
  canEdit: boolean;
  saving?: boolean;
  onChange: (status: ComparisonReviewStatus) => void;
  compact?: boolean;
};

const ACTIONS: {
  status: ComparisonReviewStatus;
  label: string;
  icon: typeof Check;
}[] = [
  { status: "REVIEWED", label: "Đã rà soát", icon: Check },
  { status: "NEEDS_ATTENTION", label: "Cần chú ý", icon: AlertTriangle },
  { status: "ACKNOWLEDGED", label: "Ghi nhận", icon: Eye },
];

export function ComparisonReviewActions({
  clauseId,
  review,
  canEdit,
  saving = false,
  onChange,
  compact = false,
}: Props) {
  const current = reviewState(review, clauseId);
  const decision = reviewDecision(review, clauseId);
  const meta = formatReviewerLine(decision);

  return (
    <section
      aria-labelledby={`review-heading-${clauseId}`}
      className={cn("flex flex-col gap-2", compact && "gap-1.5")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3
          id={`review-heading-${clauseId}`}
          className="text-caption font-semibold uppercase tracking-wide text-tertiary"
        >
          Quyết định rà soát
        </h3>
        <ReviewBadge status={current} />
      </div>
      <p className="text-caption text-tertiary">
        Quyết định của người rà soát — không thay đổi kết quả so sánh của hệ thống.
      </p>
      {meta ? <p className="text-caption text-secondary">{meta}</p> : null}
      {canEdit ? (
        <div className="flex flex-wrap gap-1.5">
          {ACTIONS.map((action) => {
            const active = current === action.status;
            const Icon = action.icon;
            return (
              <button
                key={action.status}
                type="button"
                disabled={saving || active}
                onClick={() => onChange(action.status)}
                aria-pressed={active}
                className={cn(
                  "inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-caption font-medium",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                  active
                    ? "border-accent-primary/40 bg-accent-primary/10 text-primary"
                    : "border-border-default text-secondary hover:bg-elevated hover:text-primary",
                )}
              >
                {saving && !active ? (
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
                ) : (
                  <Icon className="h-3 w-3" aria-hidden />
                )}
                {action.label}
              </button>
            );
          })}
          {current !== "OPEN" ? (
            <button
              type="button"
              disabled={saving}
              onClick={() => onChange("OPEN")}
              className={cn(
                "inline-flex h-8 items-center gap-1 rounded-md border border-border-default px-2.5",
                "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              <RotateCcw className="h-3 w-3" aria-hidden />
              Mở lại
            </button>
          ) : null}
        </div>
      ) : (
        <p className="text-caption text-tertiary">Chỉ editor trở lên mới ghi nhận rà soát.</p>
      )}
    </section>
  );
}
