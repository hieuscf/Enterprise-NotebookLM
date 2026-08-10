/**
 * =============================================================================
 * File: AdminHealthDrawer.tsx
 * Module/Service: Observability / System Health Console (Web App) — FR13
 * Layer: UI
 * Purpose: Detail drawer for a single HealthService probe result.
 * Responsibilities:
 *   - Accessible dialog; show only fields returned by the API
 * Dependencies:
 *   - features/admin/admin-health
 * Public Exports:
 *   - AdminHealthDrawer
 * Database/Table: N/A
 * Related Modules: AdminHealthView
 * Important Notes: Read-only — no restart/repair actions. No secrets.
 * =============================================================================
 */

"use client";

import { X } from "lucide-react";
import { useEffect, useId } from "react";

import {
  displayProvider,
  formatFullTs,
  formatRelativeAgo,
  HEALTH_STATUS_META,
} from "@/features/admin/admin-health";
import { cn } from "@/lib/utils";
import type { HealthService } from "@/types/admin";

type Props = {
  service: HealthService | null;
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

export function AdminHealthDrawer({ service, open, onClose }: Props) {
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

  if (!open || !service) return null;

  const meta = HEALTH_STATUS_META[service.status];
  const provider = displayProvider(service);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="presentation">
      <button
        type="button"
        aria-label="Close health details"
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
              Health Check
            </p>
            <h2 id={titleId} className="mt-1 truncate text-h3 text-primary">
              {service.name}
            </h2>
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
          <dl className="mb-5 flex flex-col gap-2 rounded-lg border border-border-default px-3 py-3">
            <MetaRow label="Status">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption font-semibold",
                  meta.badgeClass,
                )}
              >
                <span aria-hidden>{meta.marker}</span>
                {meta.label}
              </span>
            </MetaRow>
            <MetaRow label="Provider">
              <span className="font-mono">{provider ?? "—"}</span>
            </MetaRow>
            <MetaRow label="Category">
              {service.category === "core" ? "Core Infrastructure" : "AI & Retrieval"}
            </MetaRow>
            <MetaRow label="Critical">
              {service.critical ? "Yes" : "No"}
            </MetaRow>
            <MetaRow label="Last checked">
              <span title={formatFullTs(service.checked_at)}>
                {formatFullTs(service.checked_at)}
                <span className="ml-1 text-tertiary">
                  ({formatRelativeAgo(service.checked_at)})
                </span>
              </span>
            </MetaRow>
            <MetaRow label="Response">
              <span
                className="font-mono"
                title="Health-check probe latency — not a performance SLA"
              >
                {service.response_time_ms != null
                  ? `${service.response_time_ms} ms`
                  : "—"}
              </span>
            </MetaRow>
            <MetaRow label="Message">
              {service.message?.trim() || "—"}
            </MetaRow>
          </dl>

          <section className="rounded-lg border border-border-default px-3 py-3">
            <h3 className="mb-2 text-caption font-semibold uppercase tracking-wider text-tertiary">
              Technical Details
            </h3>
            <dl className="flex flex-col gap-2">
              <MetaRow label="Service ID">
                <span className="font-mono text-caption">{service.id}</span>
              </MetaRow>
              <MetaRow label="Status code">
                <span className="font-mono text-caption">{service.status}</span>
              </MetaRow>
              <MetaRow label="Checked at">
                <span className="font-mono text-caption">
                  {service.checked_at}
                </span>
              </MetaRow>
            </dl>
            <p className="mt-3 text-caption text-tertiary">
              Read-only observability. Credentials and connection strings are
              never exposed.
            </p>
          </section>
        </div>
      </aside>
    </div>
  );
}
