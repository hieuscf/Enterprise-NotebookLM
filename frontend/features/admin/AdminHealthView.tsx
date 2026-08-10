/**
 * =============================================================================
 * File: AdminHealthView.tsx
 * Module/Service: Observability / System Health Console (Web App) — FR13
 * Layer: UI
 * Purpose: System Health page at `/admin/health`.
 * Responsibilities:
 *   - Manage-only gate; compose overall / service grids / recent checks / drawer
 *   - Manual refresh only (no polling)
 * Dependencies:
 *   - AdminShell, AdminHealth*, hooks/useAdminSystemHealth
 * Public Exports:
 *   - AdminHealthView
 * Database/Table: N/A
 * Related Modules: app/admin/health/page.tsx
 * Important Notes: Availability only — not performance, cost, or pipeline history.
 *   Unknown ≠ Healthy when the API fails.
 * =============================================================================
 */

"use client";

import { RefreshCw, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { formatRelativeAgo } from "@/features/admin/admin-health";
import { AdminHealthChecksTable } from "@/features/admin/AdminHealthChecksTable";
import { AdminHealthDrawer } from "@/features/admin/AdminHealthDrawer";
import { AdminHealthOverall } from "@/features/admin/AdminHealthOverall";
import { AdminHealthServiceGrid } from "@/features/admin/AdminHealthServiceGrid";
import { AdminShell } from "@/features/admin/AdminShell";
import { SectionError } from "@/features/admin/AdminSectionState";
import { useAdminEligibleWorkspaces } from "@/hooks/useAdminEligibleWorkspaces";
import { useAdminSystemHealth } from "@/hooks/useAdminSystemHealth";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import type { HealthService } from "@/types/admin";

function UnauthorizedState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
        <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
      </span>
      <h2 className="text-h2 text-primary">
        You don&apos;t have permission to view system health.
      </h2>
      <p className="max-w-md text-body-sm text-secondary">
        System health requires Platform <strong>Manage</strong>.
      </p>
    </div>
  );
}

export function AdminHealthView() {
  const { user, loading: authLoading } = useAuth();
  const { isManage, loading: gateLoading } = useAdminEligibleWorkspaces();
  const healthData = useAdminSystemHealth();

  const [selected, setSelected] = useState<HealthService | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [nowTick, setNowTick] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNowTick(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!selected || !healthData.health) return;
    const next = healthData.health.services.find((s) => s.id === selected.id);
    if (next) setSelected(next);
  }, [healthData.health, selected]);

  const showUnauthorized = !authLoading && !gateLoading && !isManage;
  const services = healthData.health?.services ?? [];

  const updatedLabel = healthData.lastUpdatedAt
    ? formatRelativeAgo(
        new Date(healthData.lastUpdatedAt).toISOString(),
        new Date(nowTick),
      )
    : "—";

  function openService(service: HealthService) {
    setSelected(service);
    setDrawerOpen(true);
  }

  const showUnknownError =
    Boolean(healthData.error) && !healthData.health && !healthData.loading;

  return (
    <AdminShell active="health" user={user}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-tertiary">
              Admin <span className="text-tertiary">/</span>{" "}
              <span className="text-accent-primary">Health</span>
            </p>
            <h1 className="mt-1 text-h1 text-primary">System Health</h1>
            <p className="mt-1 text-body-sm text-secondary">
              Monitor the availability of core services and infrastructure
              dependencies.
            </p>
          </div>
          {!showUnauthorized ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-caption text-tertiary" aria-live="polite">
                {healthData.refreshing
                  ? "Refreshing…"
                  : `Last checked ${updatedLabel}`}
              </span>
              <button
                type="button"
                onClick={() => void healthData.reload()}
                disabled={healthData.loading || healthData.refreshing}
                aria-label="Refresh system health"
                className={cn(
                  "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-border-default bg-surface px-4",
                  "text-body-sm font-medium text-primary hover:bg-elevated disabled:opacity-50",
                )}
              >
                <RefreshCw
                  className={cn(
                    "h-4 w-4",
                    (healthData.loading || healthData.refreshing) && "animate-spin",
                  )}
                  aria-hidden
                />
                {healthData.refreshing ? "Refreshing…" : "Refresh"}
              </button>
            </div>
          ) : null}
        </div>

        {authLoading || gateLoading ? (
          <div className="flex flex-col gap-4">
            <div className="h-32 animate-pulse rounded-lg border border-border-default bg-surface" />
            <div className="grid gap-3 sm:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-28 animate-pulse rounded-lg border border-border-default bg-surface"
                />
              ))}
            </div>
          </div>
        ) : showUnauthorized ? (
          <UnauthorizedState />
        ) : showUnknownError ? (
          <section className="rounded-lg border border-border-default bg-surface px-5 py-8 text-center">
            <p className="text-h2 font-semibold text-tertiary">? Unknown</p>
            <p className="mt-2 text-body-sm text-secondary">
              Health information is currently unavailable.
            </p>
            <div className="mt-4 flex justify-center">
              <SectionError
                message="We couldn't retrieve system health."
                onRetry={() => void healthData.reload()}
                retryLabel="Try again"
              />
            </div>
          </section>
        ) : (
          <>
            {healthData.error && healthData.health ? (
              <p className="text-caption text-warning" role="status">
                Refresh failed — showing last known health. {healthData.error}
              </p>
            ) : null}

            <AdminHealthOverall
              health={healthData.health}
              loading={healthData.loading}
              nowTick={nowTick}
            />

            <AdminHealthServiceGrid
              services={services}
              loading={healthData.loading}
              nowTick={nowTick}
              onOpen={openService}
            />

            <AdminHealthChecksTable
              services={services}
              loading={healthData.loading}
              nowTick={nowTick}
              onOpen={openService}
            />

            <AdminHealthDrawer
              service={selected}
              open={drawerOpen}
              onClose={() => setDrawerOpen(false)}
            />
          </>
        )}
      </div>
    </AdminShell>
  );
}
