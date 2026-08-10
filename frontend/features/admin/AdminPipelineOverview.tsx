/**
 * =============================================================================
 * File: AdminPipelineOverview.tsx
 * Module/Service: Observability / Pipeline Console (Web App) — FR13
 * Layer: UI
 * Purpose: Status quick-filters + overview KPI strip for `/admin/pipeline`.
 * Responsibilities:
 *   - Render All / Running / Completed / Failed filter tabs
 *   - Render Running / Completed / Failed / Avg Duration cards from sample
 * Dependencies:
 *   - admin-pipeline helpers, admin-format.formatLatency
 * Public Exports:
 *   - AdminPipelineOverview
 * Database/Table: pipeline_runs (sample-derived)
 * Related Modules: AdminPipelineView
 * Important Notes: Stats are derived from a bounded recent sample — never
 *   presented as a full-workspace aggregate when capped.
 * =============================================================================
 */

"use client";

import { formatLatency } from "@/features/admin/admin-format";
import {
  derivePipelineOverview,
  formatCount,
  PIPELINE_STATUS_LABEL,
  type PipelineOverviewStats,
} from "@/features/admin/admin-pipeline";
import { cn } from "@/lib/utils";
import type { PipelineRun, PipelineStatus } from "@/types/documents";

type StatusTab = PipelineStatus | "all";

type Props = {
  runs: PipelineRun[];
  sampleCapped: boolean;
  loading: boolean;
  activeStatus: StatusTab;
  onStatusChange: (status: StatusTab) => void;
};

const TABS: { key: StatusTab; label: string }[] = [
  { key: "all", label: "All Runs" },
  { key: "running", label: "Running" },
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
];

function StatCard({
  label,
  value,
  hint,
  loading,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: string;
  hint: string;
  loading: boolean;
  tone?: "danger" | "info" | "success" | "neutral";
  active?: boolean;
  onClick?: () => void;
}) {
  const toneClass =
    tone === "danger"
      ? "border-danger/25"
      : tone === "info"
        ? "border-info/25"
        : tone === "success"
          ? "border-success/25"
          : "border-border-default";

  const className = cn(
    "flex flex-col gap-1 rounded-lg border bg-surface px-4 py-3 text-left",
    toneClass,
    onClick && "transition-colors hover:bg-elevated/60",
    active && "ring-2 ring-accent-primary/25",
  );

  const body = (
    <>
      <p className="text-caption font-semibold uppercase tracking-wider text-tertiary">
        {label}
      </p>
      {loading ? (
        <div className="h-7 w-14 animate-pulse rounded bg-elevated" />
      ) : (
        <p className="font-mono text-h2 font-semibold text-primary">{value}</p>
      )}
      <p className="text-caption text-tertiary">{hint}</p>
    </>
  );

  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={className}>
        {body}
      </button>
    );
  }
  return <div className={className}>{body}</div>;
}

function statsHint(stats: PipelineOverviewStats): string {
  if (stats.total === 0) return "No recent sample";
  return stats.sampleCapped
    ? `From latest ${formatCount(stats.total)} runs (sample)`
    : `From latest ${formatCount(stats.total)} runs`;
}

export function AdminPipelineOverview({
  runs,
  sampleCapped,
  loading,
  activeStatus,
  onStatusChange,
}: Props) {
  const stats = derivePipelineOverview(runs, sampleCapped);
  const hint = statsHint(stats);
  const avgLabel =
    stats.avgDurationMs === null ? "—" : formatLatency(stats.avgDurationMs);

  return (
    <div className="flex flex-col gap-4">
      <div
        role="tablist"
        aria-label="Pipeline run status filter"
        className="flex flex-wrap gap-1 rounded-lg border border-border-default bg-surface p-1"
      >
        {TABS.map((tab) => {
          const selected = activeStatus === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => onStatusChange(tab.key)}
              className={cn(
                "rounded-md px-3 py-1.5 text-body-sm font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
                selected
                  ? "bg-accent-primary-soft text-accent-primary"
                  : "text-secondary hover:bg-elevated hover:text-primary",
              )}
            >
              {tab.label}
              {tab.key !== "all" && !loading ? (
                <span className="ml-1.5 font-mono text-caption text-tertiary">
                  {formatCount(stats[tab.key])}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <section aria-labelledby="pipeline-overview-heading">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h2 id="pipeline-overview-heading" className="text-h3 text-primary">
            Overview
          </h2>
          <p className="text-caption text-tertiary">{loading ? "Updating…" : hint}</p>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Running"
            value={formatCount(stats.running)}
            hint="Currently processing"
            loading={loading}
            tone="info"
            active={activeStatus === "running"}
            onClick={() => onStatusChange("running")}
          />
          <StatCard
            label="Completed"
            value={formatCount(stats.completed)}
            hint="Successful runs"
            loading={loading}
            tone="success"
            active={activeStatus === "completed"}
            onClick={() => onStatusChange("completed")}
          />
          <StatCard
            label="Failed"
            value={formatCount(stats.failed)}
            hint={stats.failed > 0 ? "Requires attention" : "No failures in sample"}
            loading={loading}
            tone={stats.failed > 0 ? "danger" : "neutral"}
            active={activeStatus === "failed"}
            onClick={() => onStatusChange("failed")}
          />
          <StatCard
            label="Avg Duration"
            value={avgLabel}
            hint="Completed runs in sample"
            loading={loading}
          />
        </div>
        {stats.failed > 0 && !loading ? (
          <p className="mt-2 text-caption text-danger" role="status">
            There are failures requiring attention
            {activeStatus !== "failed" ? ` · filter “${PIPELINE_STATUS_LABEL.failed}”` : ""}.
          </p>
        ) : !loading && stats.total > 0 && stats.failed === 0 ? (
          <p className="mt-2 text-caption text-success" role="status">
            Pipeline healthy in recent sample
          </p>
        ) : null}
      </section>
    </div>
  );
}
