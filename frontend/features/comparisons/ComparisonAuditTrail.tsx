/**
 * =============================================================================
 * File: ComparisonAuditTrail.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TASK-CMP-23 read-only comparison audit history.
 * Responsibilities:
 *   - Show who did what, to which clause, when, and what changed
 *   - Optional filter to the selected clause
 * Dependencies:
 *   - comparison-audit helpers, design tokens
 * Public Exports:
 *   - ComparisonAuditTrail
 * Database/Table: N/A
 * Related Modules: ComparisonSummaryView
 * Important Notes: Not a chat/activity feed. Events are append-only.
 * =============================================================================
 */

"use client";

import { History } from "lucide-react";
import { useMemo, useState } from "react";

import {
  auditActionLabel,
  auditChangeText,
  eventsForClause,
  formatAuditTime,
  newestFirst,
} from "@/features/comparisons/comparison-audit";
import { cn } from "@/lib/utils";
import type { ComparisonAuditEvent } from "@/types/comparisons";

type Props = {
  events: ComparisonAuditEvent[];
  selectedClauseId?: string | null;
  loading?: boolean;
};

export function ComparisonAuditTrail({
  events,
  selectedClauseId = null,
  loading = false,
}: Props) {
  const [clauseOnly, setClauseOnly] = useState(false);
  const scoped = useMemo(
    () =>
      clauseOnly ? eventsForClause(events, selectedClauseId) : events,
    [clauseOnly, events, selectedClauseId],
  );
  const rows = useMemo(() => newestFirst(scoped), [scoped]);

  return (
    <section
      aria-label="Nhật ký kiểm toán"
      className="rounded-lg border border-border-default bg-elevated/40 px-4 py-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-body-sm font-semibold text-primary">
            <History className="h-4 w-4 text-tertiary" aria-hidden />
            Nhật ký kiểm toán
          </h3>
          <p className="mt-1 text-caption text-tertiary">
            Ghi nhận người thực hiện, hành động, điều khoản và thay đổi. Đây là
            nhật ký tuân thủ, không phải luồng trao đổi.
          </p>
        </div>
        <label className="inline-flex items-center gap-2 text-caption text-secondary">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 rounded border-border-default"
            checked={clauseOnly}
            disabled={!selectedClauseId}
            onChange={(event) => setClauseOnly(event.target.checked)}
          />
          Chỉ điều khoản đang chọn
        </label>
      </div>

      {loading && rows.length === 0 ? (
        <p className="mt-3 text-caption text-tertiary">Đang tải nhật ký…</p>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-caption text-tertiary">
          Chưa có hành động rà soát nào được ghi nhận.
        </p>
      ) : (
        <ol className="mt-3 max-h-72 overflow-y-auto border-t border-border-default">
          {rows.map((event) => {
            const change = auditChangeText(event);
            const active =
              selectedClauseId && event.clause_id === selectedClauseId;
            return (
              <li
                key={event.id}
                className={cn(
                  "grid gap-1 border-b border-border-default py-2.5 last:border-b-0 sm:grid-cols-[7.5rem_1fr]",
                  active && "bg-accent-primary/5",
                )}
              >
                <time
                  className="text-caption text-tertiary"
                  dateTime={event.occurred_at}
                >
                  {formatAuditTime(event.occurred_at)}
                </time>
                <div className="min-w-0">
                  <p className="text-caption text-primary">
                    <span className="font-medium">
                      {(event.actor_name || "Reviewer").trim()}
                    </span>
                    <span className="text-tertiary"> · </span>
                    {auditActionLabel(event.action)}
                    {event.clause_id ? (
                      <>
                        <span className="text-tertiary"> · </span>
                        <span className="font-mono text-secondary">
                          {event.clause_id}
                        </span>
                      </>
                    ) : null}
                  </p>
                  {change ? (
                    <p className="mt-0.5 text-caption text-secondary">{change}</p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
