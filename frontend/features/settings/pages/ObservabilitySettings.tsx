/**
 * =============================================================================
 * File: ObservabilitySettings.tsx
 * Module/Service: Settings (Web App) / Observability
 * Layer: UI
 * Purpose: System health + recent pipeline activity for Platform Manage users.
 * Responsibilities:
 *   - GET /admin/health + GET /admin/workspaces/{id}/pipeline-runs
 *   - Map services to user-facing knowledge-system labels
 * Dependencies:
 *   - lib/admin.api, lib/rbac, Settings* components
 * Public Exports:
 *   - ObservabilitySettings
 * Database/Table: pipeline_runs
 * Related Modules: app/workspaces/[id]/settings/observability/page.tsx
 * Important Notes: Never expose secrets; Platform Manage only.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getAdminSystemHealth,
  listWorkspacePipelineRuns,
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
import { cn } from "@/lib/utils";
import type { SystemHealth, SystemHealthStatus } from "@/types/admin";
import type { PipelineRun } from "@/types/documents";

type Props = {
  workspaceId: string;
};

/** Preferred display order — map known service ids/names when present. */
const DISPLAY_SERVICES: { match: RegExp; label: string }[] = [
  { match: /query.?router|router/i, label: "Query Router" },
  { match: /hybrid|retrieval|search|elastic|vector/i, label: "Hybrid Retrieval" },
  { match: /knowledge.?graph|graph|neo4j/i, label: "Knowledge Graph" },
  { match: /citation/i, label: "Citation Verification" },
  { match: /llm|anthropic|openai|model/i, label: "LLM Provider" },
];

const STATUS_LABEL: Record<SystemHealthStatus, string> = {
  healthy: "Operational",
  degraded: "Degraded",
  unhealthy: "Outage",
  unknown: "Unknown",
};

const STATUS_DOT: Record<SystemHealthStatus, string> = {
  healthy: "bg-success",
  degraded: "bg-warning",
  unhealthy: "bg-danger",
  unknown: "bg-tertiary",
};

const PIPELINE_STAGE_LABEL: Record<string, string> = {
  preview_generation: "Preview",
  document_understanding: "OCR",
  cleaning_normalize: "Cleaning",
  hierarchical_chunking: "Chunking",
  embedding: "Embedding",
  graph_extraction: "Knowledge Graph",
  indexing: "Indexing",
  ocr_cleaning: "OCR",
  chunking: "Chunking",
};

function pipelineStatusLabel(status: string): string {
  switch (status) {
    case "completed":
    case "success":
      return "Completed";
    case "failed":
    case "error":
      return "Failed";
    case "running":
    case "processing":
      return "Running";
    case "queued":
    case "pending":
      return "Queued";
    default:
      return status;
  }
}

export function ObservabilitySettings({ workspaceId }: Props) {
  const { user } = useAuth();
  const { workspace } = useSettingsWorkspace(workspaceId);
  const allowed = canAccessAdmin(user);

  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!allowed) return;
    setLoading(true);
    setError(null);
    try {
      const [healthData, pipelineRuns] = await Promise.all([
        getAdminSystemHealth(),
        listWorkspacePipelineRuns(workspaceId, { page: 1, pageSize: 12 }),
      ]);
      setHealth(healthData);
      setRuns(pipelineRuns);
    } catch (err) {
      setHealth(null);
      setRuns([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được dữ liệu quan sát hệ thống.",
      );
    } finally {
      setLoading(false);
    }
  }, [allowed, workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const serviceRows = useMemo(() => {
    const services = health?.services ?? [];
    const rows: { label: string; status: SystemHealthStatus }[] = [];

    for (const def of DISPLAY_SERVICES) {
      const found = services.find(
        (s) => def.match.test(s.id) || def.match.test(s.name),
      );
      rows.push({
        label: def.label,
        status: found?.status ?? "unknown",
      });
    }

    // If backend returned services that didn't match, append remaining once.
    for (const s of services) {
      const already = DISPLAY_SERVICES.some(
        (d) => d.match.test(s.id) || d.match.test(s.name),
      );
      if (!already) {
        rows.push({ label: s.name, status: s.status });
      }
    }

    return rows;
  }, [health]);

  const recentActivity = useMemo(() => {
    const byLabel = new Map<string, string>();
    for (const run of runs) {
      const lastStage = run.stages?.[run.stages.length - 1];
      const stageName = lastStage?.stage ?? run.status;
      const label =
        PIPELINE_STAGE_LABEL[String(stageName).toLowerCase()] ??
        String(stageName)
          .replace(/_/g, " ")
          .replace(/\b\w/g, (c) => c.toUpperCase());
      const status = lastStage?.status
        ? pipelineStatusLabel(lastStage.status)
        : pipelineStatusLabel(run.status);
      if (!byLabel.has(label)) {
        byLabel.set(label, status);
      }
    }
    if (byLabel.size === 0) {
      return [
        { label: "OCR", status: "—" },
        { label: "Indexing", status: "—" },
        { label: "Knowledge Graph", status: "—" },
      ];
    }
    return Array.from(byLabel.entries())
      .slice(0, 6)
      .map(([label, status]) => ({ label, status }));
  }, [runs]);

  return (
    <SettingsLayout
      workspaceId={workspaceId}
      active="observability"
      user={user}
      workspaceName={workspace?.name}
    >
      <SettingsHeader
        title="Quan sát hệ thống"
        description="Theo dõi sức khoẻ và độ tin cậy của hệ thống tri thức Workspace."
      />

      {!allowed ? (
        <SettingsPermissionState
          title="Chỉ dành cho quản trị nền tảng"
          description="Mục Quan sát hệ thống yêu cầu quyền Platform Manage."
        />
      ) : loading ? (
        <SettingsLoadingState message="Đang kiểm tra hệ thống…" />
      ) : error ? (
        <SettingsErrorState message={error} onRetry={() => void load()} />
      ) : (
        <>
          <SettingsSection title="Trạng thái hệ thống">
            <ul className="max-w-xl divide-y divide-border-default">
              {serviceRows.map((row) => (
                <li
                  key={row.label}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <span className="text-body-sm text-primary">{row.label}</span>
                  <span className="inline-flex items-center gap-2 text-body-sm text-secondary">
                    <span
                      aria-hidden
                      className={cn(
                        "h-2 w-2 rounded-full",
                        STATUS_DOT[row.status],
                      )}
                    />
                    {STATUS_LABEL[row.status]}
                  </span>
                </li>
              ))}
            </ul>
          </SettingsSection>

          <SettingsSection title="Hoạt động gần đây">
            <ul className="max-w-xl divide-y divide-border-default">
              {recentActivity.map((row) => (
                <li
                  key={row.label}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <span className="text-body-sm text-primary">{row.label}</span>
                  <span className="text-body-sm text-secondary">{row.status}</span>
                </li>
              ))}
            </ul>
          </SettingsSection>
        </>
      )}
    </SettingsLayout>
  );
}
