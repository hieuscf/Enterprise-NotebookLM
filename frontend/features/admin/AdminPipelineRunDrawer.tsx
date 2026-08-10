/**
 * =============================================================================
 * File: AdminPipelineRunDrawer.tsx
 * Module/Service: Observability / Pipeline Console (Web App) — FR13
 * Layer: UI
 * Purpose: Right-side detail drawer for a single pipeline run — timeline,
 *          stage metadata, and failed-run error surface.
 * Responsibilities:
 *   - Accessible dialog drawer (Escape / backdrop close, focus trap basics)
 *   - Stage timeline with expandable metadata; OCR metrics when present
 *   - Prioritize error information for failed runs
 * Dependencies:
 *   - admin-pipeline, admin-format, lucide-react
 * Public Exports:
 *   - AdminPipelineRunDrawer
 * Database/Table: pipeline_runs, pipeline_stage_logs
 * Related Modules: AdminPipelineView
 * Important Notes: No retry action — backend has no retry endpoint.
 * =============================================================================
 */

"use client";

import {
  CheckCircle2,
  Circle,
  Copy,
  Loader2,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useId, useState } from "react";

import { formatLatency } from "@/features/admin/admin-format";
import {
  currentStageOf,
  documentLabel,
  extractOcrMetrics,
  failedStageOf,
  formatFullTs,
  formatRelativeAgo,
  isOcrLikeStage,
  PIPELINE_STATUS_BADGE_CLASS,
  PIPELINE_STATUS_LABEL,
  pipelineRunDurationLabel,
  STAGE_LABEL_ANY,
  stageProgressForRun,
  versionLabel,
  type StageProgressItem,
} from "@/features/admin/admin-pipeline";
import { cn } from "@/lib/utils";
import type { PipelineRun, PipelineStageLog, PipelineStatus } from "@/types/documents";

type Props = {
  run: PipelineRun | null;
  workspaceName: string;
  open: boolean;
  onClose: () => void;
};

function stageIcon(marker: StageProgressItem["marker"]) {
  if (marker === "completed") return CheckCircle2;
  if (marker === "running") return Loader2;
  if (marker === "failed") return XCircle;
  return Circle;
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-2 text-body-sm">
      <dt className="text-tertiary">{label}</dt>
      <dd className="min-w-0 text-primary">{children}</dd>
    </div>
  );
}

function JsonValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) {
    return <span className="text-tertiary">null</span>;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span className="font-mono text-caption text-primary">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-tertiary">[]</span>;
    if (depth >= 2) {
      return (
        <pre className="overflow-x-auto rounded border border-border-default bg-elevated/50 p-2 font-mono text-caption text-secondary">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }
    return (
      <ul className="mt-1 flex flex-col gap-1 border-l border-border-default pl-3">
        {value.map((item, i) => (
          <li key={i}>
            <JsonValue value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-tertiary">{"{}"}</span>;
    if (depth >= 2) {
      return (
        <pre className="overflow-x-auto rounded border border-border-default bg-elevated/50 p-2 font-mono text-caption text-secondary">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }
    return (
      <dl className="mt-1 flex flex-col gap-1.5 border-l border-border-default pl-3">
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt className="font-mono text-caption text-tertiary">{k}</dt>
            <dd>
              <JsonValue value={v} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span className="font-mono text-caption">{String(value)}</span>;
}

function ErrorBlock({ message }: { message: string }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const long = message.length > 280;
  const shown = !long || expanded ? message : `${message.slice(0, 280)}…`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="rounded-md border border-danger/30 bg-danger-soft/40 px-3 py-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-caption font-semibold uppercase tracking-wider text-danger">
          Error
        </p>
        <button
          type="button"
          onClick={() => void copy()}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-caption text-danger hover:bg-danger/10"
          aria-label="Copy error message"
        >
          <Copy className="h-3.5 w-3.5" aria-hidden />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-caption text-danger">
        {shown}
      </pre>
      {long ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-caption font-medium text-danger underline-offset-2 hover:underline"
        >
          {expanded ? "Show less" : "Expand full error"}
        </button>
      ) : null}
    </div>
  );
}

function OcrMetricsGrid({ log }: { log: PipelineStageLog }) {
  const metrics = extractOcrMetrics(log.metadata);
  const entries = [
    { key: "Pages", value: metrics.page_count },
    { key: "Characters", value: metrics.char_count },
    { key: "Segments", value: metrics.segment_count },
    { key: "Headings", value: metrics.heading_count },
    { key: "Tables", value: metrics.table_count },
  ].filter((e) => e.value !== undefined);

  if (entries.length === 0) return null;

  return (
    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
      {entries.map((e) => (
        <div
          key={e.key}
          className="rounded border border-border-default/70 bg-elevated/40 px-2.5 py-2"
        >
          <p className="text-caption text-tertiary">{e.key}</p>
          <p className="font-mono text-body-sm font-medium text-primary">
            {e.value!.toLocaleString("en-US")}
          </p>
        </div>
      ))}
    </div>
  );
}

function StageDetails({ item }: { item: StageProgressItem }) {
  const log = item.log;
  if (!log) {
    return <p className="text-caption text-tertiary">No stage log recorded yet.</p>;
  }

  return (
    <div className="mt-2 space-y-2 rounded-md border border-border-default bg-elevated/30 px-3 py-2.5">
      <p className="text-caption font-semibold uppercase tracking-wider text-tertiary">
        Stage Metadata
      </p>
      <dl className="flex flex-col gap-1.5">
        <MetaRow label="Duration">
          <span className="font-mono">
            {log.duration_ms != null ? `${log.duration_ms.toLocaleString("en-US")} ms` : "—"}
          </span>
        </MetaRow>
        <MetaRow label="Status">{PIPELINE_STATUS_LABEL[log.status as PipelineStatus]}</MetaRow>
      </dl>
      {isOcrLikeStage(log.stage) ? <OcrMetricsGrid log={log} /> : null}
      {log.metadata && Object.keys(log.metadata).length > 0 ? (
        <div>
          <p className="mb-1 text-caption text-tertiary">Metadata</p>
          <JsonValue value={log.metadata} />
        </div>
      ) : (
        <p className="text-caption text-tertiary">No metadata for this stage.</p>
      )}
      {log.error_message ? <ErrorBlock message={log.error_message} /> : null}
    </div>
  );
}

export function AdminPipelineRunDrawer({ run, workspaceName, open, onClose }: Props) {
  const titleId = useId();
  const [selectedStage, setSelectedStage] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!run) {
      setSelectedStage(null);
      return;
    }
    const failed = failedStageOf(run);
    const current = currentStageOf(run);
    setSelectedStage(failed?.stage ?? current?.stage ?? null);
  }, [run]);

  if (!open || !run) return null;

  const progress = stageProgressForRun(run);
  const failedLog = failedStageOf(run);
  const errorMessage = run.error_message ?? failedLog?.error_message ?? null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="presentation">
      <button
        type="button"
        aria-label="Close pipeline run details"
        className="absolute inset-0 bg-slate-950/40"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative flex h-full w-full max-w-md flex-col border-l border-border-default bg-surface shadow-xl"
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border-default px-5 py-4">
          <div className="min-w-0">
            <p className="text-caption font-medium uppercase tracking-wider text-tertiary">
              Pipeline Run
            </p>
            <h2 id={titleId} className="mt-1 truncate text-h3 text-primary">
              {documentLabel(run)}
            </h2>
            <p className="text-caption text-secondary">
              Version {versionLabel(run).replace(/^v/, "")} · {workspaceName}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-secondary hover:bg-elevated"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {run.status === "failed" && errorMessage ? (
            <div className="mb-5 space-y-2">
              <p className="text-body-sm font-semibold text-danger">Pipeline failed</p>
              {failedLog ? (
                <p className="text-caption text-secondary">
                  {STAGE_LABEL_ANY[failedLog.stage]} · Failed
                  {failedLog.duration_ms != null
                    ? ` after ${formatLatency(failedLog.duration_ms)}`
                    : ""}
                </p>
              ) : null}
              <ErrorBlock message={errorMessage} />
            </div>
          ) : null}

          <dl className="mb-5 flex flex-col gap-2 rounded-lg border border-border-default px-3 py-3">
            <MetaRow label="Status">
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-caption font-semibold",
                  PIPELINE_STATUS_BADGE_CLASS[run.status],
                )}
              >
                {PIPELINE_STATUS_LABEL[run.status]}
              </span>
            </MetaRow>
            <MetaRow label="Run ID">
              <span className="break-all font-mono text-caption">{run.id}</span>
            </MetaRow>
            <MetaRow label="Started">
              <span title={formatFullTs(run.started_at)}>
                {formatFullTs(run.started_at)}
                {run.started_at ? (
                  <span className="ml-1 text-tertiary">
                    ({formatRelativeAgo(run.started_at)})
                  </span>
                ) : null}
              </span>
            </MetaRow>
            <MetaRow label="Completed">
              {run.completed_at ? formatFullTs(run.completed_at) : "—"}
            </MetaRow>
            <MetaRow label="Duration">
              <span className="font-mono">{pipelineRunDurationLabel(run)}</span>
            </MetaRow>
            <MetaRow label="Retries">
              <span className="font-mono">{run.retry_count}</span>
            </MetaRow>
          </dl>

          {run.status === "running" ? (
            <p className="mb-3 text-body-sm text-info" role="status">
              Running for {pipelineRunDurationLabel(run).replace(" · running", "")}
            </p>
          ) : null}

          <h3 className="mb-2 text-caption font-semibold uppercase tracking-wider text-tertiary">
            Stage timeline
          </h3>
          <ol className="flex flex-col gap-2" aria-label="Pipeline stage timeline">
            {progress.map((item, index) => {
              const Icon = stageIcon(item.marker);
              const selected = selectedStage === item.stage;
              return (
                <li key={item.stage}>
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedStage((prev) => (prev === item.stage ? null : item.stage))
                    }
                    className={cn(
                      "flex w-full items-start gap-3 rounded-md border px-3 py-2.5 text-left transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
                      selected
                        ? "border-accent-primary/40 bg-accent-primary-soft/40"
                        : "border-border-default/70 hover:bg-elevated/50",
                      item.marker === "failed" && "border-danger/30",
                      item.marker === "running" && "border-info/30",
                    )}
                  >
                    <span className="font-mono text-caption text-tertiary">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <Icon
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0",
                        item.marker === "completed" && "text-success",
                        item.marker === "running" && "animate-spin text-info",
                        item.marker === "failed" && "text-danger",
                        (item.marker === "pending" || item.marker === "skipped") &&
                          "text-tertiary",
                      )}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className="text-body-sm font-medium text-primary">
                          {item.label}
                        </span>
                        <span className="font-mono text-caption text-tertiary">
                          {item.log?.duration_ms != null
                            ? formatLatency(item.log.duration_ms)
                            : item.marker === "running"
                              ? "…"
                              : "—"}
                        </span>
                      </div>
                      <p className="text-caption text-secondary">
                        {item.marker === "completed" && "✓ Completed"}
                        {item.marker === "running" && "● Running"}
                        {item.marker === "failed" && "✕ Failed"}
                        {item.marker === "pending" && "○ Pending"}
                        {item.marker === "skipped" && "○ Skipped"}
                      </p>
                    </div>
                  </button>
                  {selected ? <StageDetails item={item} /> : null}
                </li>
              );
            })}
          </ol>
        </div>
      </aside>
    </div>
  );
}
