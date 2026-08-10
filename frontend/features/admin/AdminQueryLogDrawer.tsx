/**
 * =============================================================================
 * File: AdminQueryLogDrawer.tsx
 * Module/Service: Observability / Query Logs Console (Web App) — FR13
 * Layer: UI
 * Purpose: Right-side detail drawer for a single query_logs audit row.
 * Responsibilities:
 *   - Show full query text, route decision explanation, LLM invariants
 *   - Technical metadata with copy-ID actions (read-only)
 * Dependencies:
 *   - features/admin/admin-query-logs, lucide-react
 * Public Exports:
 *   - AdminQueryLogDrawer
 * Database/Table: query_logs
 * Important Notes: Query logs are read-only audit data. Frontend never
 *   re-classifies route_type. workspace_id comes from console scope (OpenAPI
 *   QueryLog schema does not include workspace_id on the row).
 * =============================================================================
 */

"use client";

import { AlertTriangle, Copy, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import {
  expectedLlmCalls,
  formatFullTs,
  formatLatency,
  formatRelativeAgo,
  hasRoutingInvariantViolation,
  LATENCY_WARN_MS,
  ROUTE_BADGE_CLASS,
  ROUTE_LABEL,
  ROUTE_MARKER,
  routingDecisionCopy,
  shortId,
} from "@/features/admin/admin-query-logs";
import { cn } from "@/lib/utils";
import type { QueryLogItem } from "@/types/admin";

type Props = {
  log: QueryLogItem | null;
  workspaceId: string;
  workspaceName: string;
  open: boolean;
  onClose: () => void;
};

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-2 text-body-sm">
      <dt className="text-tertiary">{label}</dt>
      <dd className="min-w-0 text-primary">{children}</dd>
    </div>
  );
}

function CopyIdButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <button
      type="button"
      onClick={() => void copy()}
      aria-label={`Copy ${label}`}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-caption text-secondary hover:bg-elevated hover:text-primary"
    >
      <Copy className="h-3 w-3" aria-hidden />
      {copied ? "Copied" : "Copy ID"}
    </button>
  );
}

function IdValue({ value, label }: { value: string | null | undefined; label: string }) {
  if (!value) return <span className="text-tertiary">—</span>;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className="break-all font-mono text-caption">{value}</span>
      <CopyIdButton value={value} label={label} />
    </div>
  );
}

export function AdminQueryLogDrawer({
  log,
  workspaceId,
  workspaceName,
  open,
  onClose,
}: Props) {
  const titleId = useId();

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

  if (!open || !log) return null;

  const decision = routingDecisionCopy(log.route_type);
  const expected = expectedLlmCalls(log.route_type);
  const violation = hasRoutingInvariantViolation(log);
  const latencyHigh =
    log.latency_ms != null && log.latency_ms >= LATENCY_WARN_MS;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="presentation">
      <button
        type="button"
        aria-label="Close query log details"
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
              Query Log
            </p>
            <h2 id={titleId} className="mt-1 text-h3 text-primary">
              {ROUTE_LABEL[log.route_type]}
            </h2>
            <p className="text-caption text-secondary">
              {workspaceName} · {formatRelativeAgo(log.created_at)}
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
          {violation ? (
            <div
              role="status"
              className="mb-4 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 px-3 py-2.5 text-body-sm text-warning"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <div>
                <p className="font-semibold">Routing invariant violation</p>
                <p className="mt-0.5 text-caption text-secondary">
                  Expected {expected.label} LLM call(s) for{" "}
                  {ROUTE_LABEL[log.route_type]}; actual is {log.llm_calls_count}.
                  Data is shown as recorded — not corrected.
                </p>
              </div>
            </div>
          ) : null}

          <section className="mb-5">
            <h3 className="mb-2 text-caption font-semibold uppercase tracking-wider text-tertiary">
              Query
            </h3>
            <blockquote className="rounded-md border border-border-default bg-elevated/30 px-3 py-3 text-body-sm leading-relaxed text-primary">
              &ldquo;{log.query_text}&rdquo;
            </blockquote>
          </section>

          <dl className="mb-5 flex flex-col gap-2 rounded-lg border border-border-default px-3 py-3">
            <MetaRow label="Route">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption font-semibold",
                  ROUTE_BADGE_CLASS[log.route_type],
                )}
              >
                <span aria-hidden>{ROUTE_MARKER[log.route_type]}</span>
                {ROUTE_LABEL[log.route_type]}
              </span>
            </MetaRow>
            <MetaRow label="LLM Calls">
              <span className="font-mono">{log.llm_calls_count}</span>
            </MetaRow>
            <MetaRow label="Model">
              <span className="font-mono">{log.model_used ?? "—"}</span>
            </MetaRow>
            <MetaRow label="Latency">
              <span
                className={cn(
                  "font-mono",
                  latencyHigh ? "text-warning" : "text-primary",
                )}
                title={
                  latencyHigh
                    ? `Above presentation threshold (${LATENCY_WARN_MS} ms) — not an SLA`
                    : undefined
                }
              >
                {formatLatency(log.latency_ms)}
              </span>
            </MetaRow>
            <MetaRow label="Created">
              <span title={formatFullTs(log.created_at)}>
                {formatFullTs(log.created_at)}
              </span>
            </MetaRow>
            <MetaRow label="User">
              <IdValue value={log.user_id} label="user ID" />
            </MetaRow>
            <MetaRow label="Workspace">
              <div className="flex min-w-0 flex-col gap-0.5">
                <span>{workspaceName}</span>
                <IdValue value={workspaceId} label="workspace ID" />
              </div>
            </MetaRow>
            <MetaRow label="Message ID">
              <IdValue value={log.message_id} label="message ID" />
            </MetaRow>
            <MetaRow label="Cache ID">
              <IdValue value={log.cache_id} label="cache ID" />
            </MetaRow>
          </dl>

          <section className="mb-5 rounded-lg border border-border-default px-3 py-3">
            <h3 className="mb-2 text-caption font-semibold uppercase tracking-wider text-tertiary">
              Routing Decision
            </h3>
            <p className="text-body-sm font-medium text-primary">{decision.title}</p>
            <p className="mt-1 text-body-sm text-secondary">{decision.body}</p>
            <dl className="mt-3 flex flex-col gap-1.5 border-t border-border-default pt-3">
              <MetaRow label="Expected LLM">
                <span className="font-mono">{decision.expectedLabel}</span>
              </MetaRow>
              <MetaRow label="Actual LLM">
                <span className="font-mono">{log.llm_calls_count}</span>
              </MetaRow>
            </dl>
            <p className="mt-2 text-caption text-tertiary">
              Explanation of the route type recorded by the backend — frontend
              does not re-run Query Router classification.
            </p>
          </section>

          {(log.message_id || log.cache_id) && (
            <section className="mb-5 rounded-lg border border-border-default px-3 py-3">
              <h3 className="mb-2 text-caption font-semibold uppercase tracking-wider text-tertiary">
                Relationships
              </h3>
              <dl className="flex flex-col gap-2">
                <MetaRow label="Related Message">
                  <IdValue value={log.message_id} label="message ID" />
                </MetaRow>
                <MetaRow label="Cache Entry">
                  <IdValue value={log.cache_id} label="cache ID" />
                </MetaRow>
              </dl>
            </section>
          )}

          <section className="rounded-lg border border-border-default px-3 py-3">
            <h3 className="mb-2 text-caption font-semibold uppercase tracking-wider text-tertiary">
              Technical Details
            </h3>
            <dl className="flex flex-col gap-2">
              <MetaRow label="Query Log ID">
                <IdValue value={log.id} label="query log ID" />
              </MetaRow>
              <MetaRow label="Workspace ID">
                <IdValue value={workspaceId} label="workspace ID" />
              </MetaRow>
              <MetaRow label="User ID">
                <IdValue value={log.user_id} label="user ID" />
              </MetaRow>
              <MetaRow label="Message ID">
                <IdValue value={log.message_id} label="message ID" />
              </MetaRow>
              <MetaRow label="Cache ID">
                <IdValue value={log.cache_id} label="cache ID" />
              </MetaRow>
              <MetaRow label="Route Type">
                <span className="font-mono text-caption">{log.route_type}</span>
              </MetaRow>
              <MetaRow label="LLM Calls">
                <span className="font-mono">{log.llm_calls_count}</span>
              </MetaRow>
              <MetaRow label="Model">
                <span className="font-mono">{log.model_used ?? "—"}</span>
              </MetaRow>
              <MetaRow label="Latency">
                <span className="font-mono">
                  {log.latency_ms != null
                    ? `${log.latency_ms.toLocaleString("en-US")} ms`
                    : "—"}
                </span>
              </MetaRow>
              <MetaRow label="Created At">
                <span className="font-mono text-caption">
                  {formatFullTs(log.created_at)}
                </span>
              </MetaRow>
            </dl>
            <p className="mt-3 text-caption text-tertiary">
              Short ID: <span className="font-mono">{shortId(log.id)}</span>
            </p>
          </section>
        </div>
      </aside>
    </div>
  );
}
