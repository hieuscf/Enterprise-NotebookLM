/**
 * =============================================================================
 * File: UsageSettings.tsx
 * Module/Service: Settings (Web App) / Observability
 * Layer: UI
 * Purpose: Workspace AI usage & cost summary for Platform Manage users.
 * Responsibilities:
 *   - Call GET /admin/workspaces/{id}/cost-summary
 *   - Show LLM requests, cost, latency, Query Router breakdown
 * Dependencies:
 *   - lib/admin.api, lib/rbac, Settings* components
 * Public Exports:
 *   - UsageSettings
 * Database/Table: message_generations, query_logs
 * Related Modules: app/workspaces/[id]/settings/usage/page.tsx
 * Important Notes: Platform Manage only — mirrors Admin Console contract.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getWorkspaceCostSummary,
} from "@/lib/admin.api";
import { SettingsErrorState } from "@/features/settings/SettingsErrorState";
import { SettingsHeader } from "@/features/settings/SettingsHeader";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { SettingsLoadingState } from "@/features/settings/SettingsLoadingState";
import { SettingsPermissionState } from "@/features/settings/SettingsPermissionState";
import { SettingsSection } from "@/features/settings/SettingsSection";
import { useSettingsWorkspace } from "@/features/settings/useSettingsWorkspace";
import { useAuth } from "@/hooks/useAuth";
import { ApiClientError } from "@/lib/api-client";
import { canAccessAdmin } from "@/lib/rbac";
import type { CostSummary } from "@/types/admin";
import type { RouteType } from "@/types/chat";

type Props = {
  workspaceId: string;
};

const ROUTE_ORDER: RouteType[] = [
  "cache_hit",
  "metadata",
  "section_extraction",
  "factoid",
  "complex",
];

const ROUTE_LABEL: Record<RouteType, string> = {
  cache_hit: "Cache Hit",
  metadata: "Metadata",
  section_extraction: "Section Extraction",
  factoid: "Factoid",
  complex: "Complex",
};

function monthRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  return {
    from: from.toISOString().slice(0, 10),
    to: now.toISOString().slice(0, 10),
  };
}

function formatUsd(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(n);
}

function formatLatency(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function UsageSettings({ workspaceId }: Props) {
  const { user } = useAuth();
  const { workspace } = useSettingsWorkspace(workspaceId);
  const allowed = canAccessAdmin(user);

  const [summary, setSummary] = useState<CostSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const range = useMemo(() => monthRange(), []);

  const load = useCallback(async () => {
    if (!allowed) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getWorkspaceCostSummary(workspaceId, range);
      setSummary(data);
    } catch (err) {
      setSummary(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được dữ liệu sử dụng.",
      );
    } finally {
      setLoading(false);
    }
  }, [allowed, workspaceId, range]);

  useEffect(() => {
    void load();
  }, [load]);

  const routeBreakdown = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of summary?.by_route_type ?? []) {
      map.set(row.route_type, row.count);
    }
    const total = ROUTE_ORDER.reduce((acc, key) => acc + (map.get(key) ?? 0), 0);
    return ROUTE_ORDER.map((key) => {
      const count = map.get(key) ?? 0;
      const pct = total > 0 ? Math.round((count / total) * 100) : 0;
      return { key, count, pct };
    });
  }, [summary]);

  const avgLatencyMs = useMemo(() => {
    if (!summary) return null;
    const agents = Object.values(summary.by_agent_type ?? {});
    if (agents.length === 0) return null;
    const totalCount = agents.reduce((a, b) => a + b.count, 0);
    if (totalCount === 0) return null;
    const totalLatency = agents.reduce((a, b) => a + b.total_latency_ms, 0);
    return totalLatency / totalCount;
  }, [summary]);

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="usage"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="Sử dụng & chi phí"
        description="Theo dõi mức sử dụng AI của Workspace trong tháng này."
      />

      {!allowed ? (
        <SettingsPermissionState
          title="Chỉ dành cho quản trị nền tảng"
          description="Mục Sử dụng & chi phí yêu cầu quyền Platform Manage. Liên hệ quản trị viên hệ thống hoặc mở Admin Console."
        />
      ) : loading ? (
        <SettingsLoadingState message="Đang tải số liệu…" />
      ) : error ? (
        <SettingsErrorState message={error} onRetry={() => void load()} />
      ) : summary ? (
        <>
          <SettingsSection title="Sử dụng AI Workspace" description="Tháng này">
            <div className="grid max-w-2xl grid-cols-1 gap-4 sm:grid-cols-3">
              <Metric
                label="LLM requests"
                value={summary.total_llm_calls.toLocaleString("en-US")}
              />
              <Metric
                label="Chi phí ước tính"
                value={formatUsd(summary.total_cost_usd)}
              />
              <Metric
                label="Độ trễ trung bình"
                value={formatLatency(avgLatencyMs)}
              />
            </div>
          </SettingsSection>

          <SettingsSection
            title="Query routing"
            description="Phân bổ theo Query Router: cache_hit · metadata · section_extraction · factoid · complex."
          >
            <ul className="max-w-xl divide-y divide-border-default">
              {routeBreakdown.map((row) => (
                <li
                  key={row.key}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <span className="text-body-sm text-primary">
                    {ROUTE_LABEL[row.key]}
                  </span>
                  <span className="tabular-nums text-body-sm text-secondary">
                    {row.pct}%
                    <span className="ml-2 text-caption text-tertiary">
                      ({row.count})
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </SettingsSection>
        </>
      ) : null}
    </SettingsLayout>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border-default px-4 py-4">
      <p className="text-caption text-tertiary">{label}</p>
      <p className="mt-1.5 text-h2 tabular-nums text-primary">{value}</p>
    </div>
  );
}
