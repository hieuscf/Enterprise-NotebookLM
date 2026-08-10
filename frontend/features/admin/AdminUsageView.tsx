/**
 * =============================================================================
 * File: AdminUsageView.tsx
 * Module/Service: Observability / Usage Console (Web App) — FR13
 * Layer: UI
 * Purpose: LLM Usage & Cost Dashboard at `/admin/usage`.
 * Responsibilities:
 *   - Manage-only gate; sync workspace / date range to URL
 *   - Compose date range, KPIs, overview, model/route panels, breakdown
 *   - Manual refresh only (no polling)
 * Dependencies:
 *   - AdminShell, AdminUsage*, hooks/useAdminUsageConsole
 * Public Exports:
 *   - AdminUsageView
 * Database/Table: message_generations (via CostSummary)
 * Related Modules: app/admin/usage/page.tsx
 * Important Notes: CostSummary API is the source of truth. Not query-logs,
 *   not billing, not pipeline monitoring.
 * =============================================================================
 */

"use client";

import { RefreshCw, ShieldAlert } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { formatRelativeAgo } from "@/features/admin/admin-pipeline";
import {
  parseUsagePreset,
  resolveUsageDateRange,
  USAGE_DATE_PRESETS,
  type UsageDatePreset,
} from "@/features/admin/admin-usage";
import { AdminShell } from "@/features/admin/AdminShell";
import { AdminUsageBreakdown } from "@/features/admin/AdminUsageBreakdown";
import { AdminUsageByModel } from "@/features/admin/AdminUsageByModel";
import { AdminUsageByRoute } from "@/features/admin/AdminUsageByRoute";
import { AdminUsageDateRange } from "@/features/admin/AdminUsageDateRange";
import { AdminUsageKpis } from "@/features/admin/AdminUsageKpis";
import { AdminUsageOverview } from "@/features/admin/AdminUsageOverview";
import { SectionError } from "@/features/admin/AdminSectionState";
import { useAdminEligibleWorkspaces } from "@/hooks/useAdminEligibleWorkspaces";
import { useAdminUsageConsole } from "@/hooks/useAdminUsageConsole";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

function UnauthorizedState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
        <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
      </span>
      <h2 className="text-h2 text-primary">
        You don&apos;t have permission to view usage data.
      </h2>
      <p className="max-w-md text-body-sm text-secondary">
        LLM usage &amp; cost requires Platform <strong>Manage</strong>.
      </p>
    </div>
  );
}

export function AdminUsageView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const {
    options: workspaceOptions,
    isManage,
    loading: gateLoading,
  } = useAdminEligibleWorkspaces();

  const preset = parseUsagePreset(searchParams.get("preset"));
  const urlFrom = searchParams.get("from") ?? "";
  const urlTo = searchParams.get("to") ?? "";
  const workspaceParam = searchParams.get("workspace") ?? "";

  const [customFrom, setCustomFrom] = useState(urlFrom);
  const [customTo, setCustomTo] = useState(urlTo);
  const [nowTick, setNowTick] = useState(() => Date.now());

  const resolved = useMemo(() => {
    if (preset === "custom" && urlFrom && urlTo) {
      return resolveUsageDateRange("custom", urlFrom, urlTo);
    }
    return resolveUsageDateRange(preset, urlFrom, urlTo);
  }, [preset, urlFrom, urlTo]);

  const selectedWorkspaceId = useMemo(() => {
    if (workspaceParam && workspaceOptions.some((w) => w.id === workspaceParam)) {
      return workspaceParam;
    }
    return workspaceOptions[0]?.id ?? "";
  }, [workspaceParam, workspaceOptions]);

  const replaceParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      }
      const qs = next.toString();
      router.replace(qs ? `/admin/usage?${qs}` : "/admin/usage", { scroll: false });
    },
    [router, searchParams],
  );

  useEffect(() => {
    if (!selectedWorkspaceId) return;
    if (workspaceParam === selectedWorkspaceId) return;
    if (workspaceParam && workspaceOptions.some((w) => w.id === workspaceParam)) {
      return;
    }
    replaceParams({ workspace: selectedWorkspaceId });
  }, [selectedWorkspaceId, workspaceParam, workspaceOptions, replaceParams]);

  // Keep from/to in URL for non-custom presets so refresh/share is stable.
  useEffect(() => {
    if (preset === "custom") return;
    if (urlFrom === resolved.from && urlTo === resolved.to) return;
    replaceParams({ from: resolved.from, to: resolved.to, preset });
  }, [preset, resolved.from, resolved.to, urlFrom, urlTo, replaceParams]);

  useEffect(() => {
    setCustomFrom(urlFrom || resolved.from);
    setCustomTo(urlTo || resolved.to);
  }, [urlFrom, urlTo, resolved.from, resolved.to]);

  const consoleData = useAdminUsageConsole({
    workspaceId: selectedWorkspaceId || null,
    from: resolved.from,
    to: resolved.to,
  });

  useEffect(() => {
    const id = window.setInterval(() => setNowTick(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);

  const showUnauthorized = !authLoading && !gateLoading && !isManage;

  const updatedLabel = consoleData.lastUpdatedAt
    ? formatRelativeAgo(
        new Date(consoleData.lastUpdatedAt).toISOString(),
        new Date(nowTick),
      )
    : "—";

  const periodLabel =
    USAGE_DATE_PRESETS.find((p) => p.value === preset)?.label ?? "Custom";

  function handlePresetChange(next: UsageDatePreset) {
    if (next === "custom") {
      replaceParams({
        preset: "custom",
        from: customFrom || resolved.from,
        to: customTo || resolved.to,
      });
      return;
    }
    const range = resolveUsageDateRange(next);
    replaceParams({
      preset: next,
      from: range.from,
      to: range.to,
    });
  }

  function handleApplyCustom() {
    const range = resolveUsageDateRange("custom", customFrom, customTo);
    replaceParams({
      preset: "custom",
      from: range.from,
      to: range.to,
    });
  }

  const showBodySkeleton = consoleData.loading && !consoleData.summary;

  return (
    <AdminShell active="usage" user={user}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-tertiary">
              Admin <span className="text-tertiary">/</span>{" "}
              <span className="text-accent-primary">Usage</span>
            </p>
            <h1 className="mt-1 text-h1 text-primary">Usage</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Monitor LLM usage, cost, and routing efficiency across the
              workspace.
            </p>
          </div>
          {!showUnauthorized ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-caption text-tertiary" aria-live="polite">
                Updated {updatedLabel}
              </span>
              <button
                type="button"
                onClick={() => void consoleData.reload()}
                disabled={consoleData.loading}
                aria-label="Refresh usage data"
                className={cn(
                  "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-border-default bg-surface px-4",
                  "text-body-sm font-medium text-primary hover:bg-elevated disabled:opacity-50",
                )}
              >
                <RefreshCw
                  className={cn("h-4 w-4", consoleData.loading && "animate-spin")}
                  aria-hidden
                />
                Refresh
              </button>
            </div>
          ) : null}
        </div>

        {authLoading || gateLoading ? (
          <div className="flex flex-col gap-4">
            <div className="h-28 animate-pulse rounded-lg border border-border-default bg-surface" />
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-24 animate-pulse rounded-lg border border-border-default bg-surface"
                />
              ))}
            </div>
            <div className="h-48 animate-pulse rounded-lg border border-border-default bg-surface" />
          </div>
        ) : showUnauthorized ? (
          <UnauthorizedState />
        ) : workspaceOptions.length === 0 ? (
          <div className="rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
            <p className="text-body-sm font-medium text-secondary">
              No workspaces available
            </p>
            <p className="mt-1 text-caption text-tertiary">
              Create a workspace before reviewing LLM usage.
            </p>
          </div>
        ) : (
          <>
            <AdminUsageDateRange
              workspaceId={selectedWorkspaceId}
              workspaceOptions={workspaceOptions}
              preset={preset}
              from={resolved.from}
              to={resolved.to}
              customFrom={customFrom}
              customTo={customTo}
              loading={consoleData.loading}
              onWorkspaceChange={(id) =>
                replaceParams({ workspace: id || null })
              }
              onPresetChange={handlePresetChange}
              onCustomFromChange={setCustomFrom}
              onCustomToChange={setCustomTo}
              onApplyCustom={handleApplyCustom}
            />

            {consoleData.error && !consoleData.summary ? (
              <SectionError
                message="Unable to load usage data. We couldn't retrieve LLM usage for this period."
                onRetry={() => void consoleData.reload()}
                retryLabel="Try again"
              />
            ) : (
              <>
                <AdminUsageKpis
                  summary={consoleData.summary}
                  from={resolved.from}
                  to={resolved.to}
                  periodLabel={periodLabel}
                  loading={showBodySkeleton}
                />

                <AdminUsageOverview
                  summary={consoleData.summary}
                  loading={showBodySkeleton}
                  periodLabel={periodLabel}
                />

                <div className="grid gap-4 lg:grid-cols-2">
                  <AdminUsageByModel
                    summary={consoleData.summary}
                    loading={showBodySkeleton}
                  />
                  <AdminUsageByRoute
                    summary={consoleData.summary}
                    loading={showBodySkeleton}
                  />
                </div>

                <AdminUsageBreakdown
                  summary={consoleData.summary}
                  loading={showBodySkeleton}
                />
              </>
            )}
          </>
        )}
      </div>
    </AdminShell>
  );
}
