/**
 * =============================================================================
 * File: AdminDocumentDetailView.tsx
 * Module/Service: Admin Document Management (Web App) — FR2 / FR12
 * Layer: UI
 * Purpose: Document operations detail at `/admin/documents/{documentId}`.
 * Responsibilities:
 *   - Load GET /admin/documents/{id} + versions; show workspace / version /
 *     pipeline diagnosis for Manage
 * Dependencies:
 *   - AdminShell, AdminCard, admin-documents, pipeline-stages, admin.api
 * Public Exports:
 *   - AdminDocumentDetailView
 * Database/Table: documents, document_versions, pipeline_runs
 * Related Modules: app/admin/documents/[documentId]/page.tsx
 * Important Notes: No content preview, no retry (no retry API), no delete.
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Circle,
  Loader2,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import {
  FILE_TYPE_LABEL,
  VERSION_STATUS_CLASS,
  VERSION_STATUS_LABEL,
  VERSION_STATUS_MARKER,
  formatAdminFileSize,
  formatFullTimestamp,
} from "@/features/admin/admin-documents";
import { formatLatency } from "@/features/admin/admin-format";
import { AdminCard } from "@/features/admin/AdminCard";
import { AdminShell } from "@/features/admin/AdminShell";
import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import { useAuth } from "@/hooks/useAuth";
import {
  getAdminDocument,
  listAdminDocumentVersions,
} from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import {
  PIPELINE_STAGE_ORDER,
  STAGE_LABEL_VI,
} from "@/lib/pipeline-stages";
import { canAccessAdmin } from "@/lib/rbac";
import { cn } from "@/lib/utils";
import type { AdminDocumentDetail } from "@/types/admin";
import type {
  DocumentVersion,
  DocumentVersionStatus,
  PipelineStageLog,
  PipelineStageNameV3,
  PipelineStatus,
} from "@/types/documents";

const PIPELINE_STATUS_LABEL: Record<PipelineStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

type Props = {
  documentId: string;
};

function StatusLine({ status }: { status: DocumentVersionStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-body-sm font-medium",
        VERSION_STATUS_CLASS[status],
      )}
      aria-label={`Status: ${VERSION_STATUS_LABEL[status]}`}
    >
      <span aria-hidden>{VERSION_STATUS_MARKER[status]}</span>
      {VERSION_STATUS_LABEL[status]}
    </span>
  );
}

function MetaRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3 border-b border-border-default/60 py-2 last:border-0 sm:grid-cols-[10rem_1fr]">
      <dt className="text-caption font-medium uppercase tracking-wider text-tertiary">
        {label}
      </dt>
      <dd className="min-w-0 text-body-sm text-primary">{children}</dd>
    </div>
  );
}

function stageStatusIcon(status: PipelineStatus) {
  if (status === "completed") return CheckCircle2;
  if (status === "running") return Loader2;
  if (status === "failed") return XCircle;
  return Circle;
}

function PipelineStages({ stages }: { stages: PipelineStageLog[] }) {
  const byStage = new Map(stages.map((s) => [s.stage, s]));
  const known = PIPELINE_STAGE_ORDER.filter((s) => byStage.has(s));
  if (known.length === 0) {
    return (
      <p className="text-body-sm text-tertiary">
        No stage logs available for this pipeline run yet.
      </p>
    );
  }
  return (
    <ol className="flex flex-col gap-2" aria-label="Pipeline stages">
      {known.map((stage: PipelineStageNameV3) => {
        const log = byStage.get(stage)!;
        const Icon = stageStatusIcon(log.status);
        return (
          <li
            key={stage}
            className="flex items-start gap-2.5 rounded-md border border-border-default/70 px-3 py-2"
          >
            <Icon
              className={cn(
                "mt-0.5 h-4 w-4 shrink-0",
                log.status === "completed" && "text-success",
                log.status === "running" && "animate-spin text-accent-primary",
                log.status === "failed" && "text-danger",
                log.status === "pending" && "text-tertiary",
              )}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-body-sm font-medium text-primary">
                  {STAGE_LABEL_VI[stage]}
                </span>
                <span className="text-caption text-tertiary">
                  {PIPELINE_STATUS_LABEL[log.status]}
                  {log.duration_ms != null ? ` · ${formatLatency(log.duration_ms)}` : ""}
                </span>
              </div>
              {log.status === "failed" && log.error_message ? (
                <p className="mt-1 text-caption text-danger">{log.error_message}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function AdminDocumentDetailView({ documentId }: Props) {
  const { user, loading: authLoading } = useAuth();
  const isManage = canAccessAdmin(user);

  const [detail, setDetail] = useState<AdminDocumentDetail | null>(null);
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (authLoading) return;
    if (!isManage) {
      setLoading(false);
      setError(null);
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [doc, vers] = await Promise.all([
        getAdminDocument(documentId),
        listAdminDocumentVersions(documentId),
      ]);
      setDetail(doc);
      setVersions(vers);
    } catch (err) {
      setDetail(null);
      setVersions([]);
      if (err instanceof ApiClientError) {
        if (err.status === 404) setError("Document not found.");
        else if (err.status === 403) {
          setError("You don't have permission to view this document.");
        } else {
          setError("Unable to load document detail.");
        }
      } else {
        setError("Unable to load document detail.");
      }
    } finally {
      setLoading(false);
    }
  }, [authLoading, isManage, documentId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Poll detail lightly while processing.
  useEffect(() => {
    if (!detail || detail.current_version?.status !== "processing") return;
    const id = window.setInterval(() => {
      void reload();
    }, 10_000);
    return () => window.clearInterval(id);
  }, [detail, reload]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace("#", "");
    if (!hash) return;
    const el = document.getElementById(hash);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [detail]);

  const pipeline = detail?.latest_pipeline_run ?? null;
  const current = detail?.current_version ?? null;
  const failed =
    current?.status === "failed" || pipeline?.status === "failed";

  return (
    <AdminShell active="documents" user={user}>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <Link
          href="/admin/documents"
          className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium text-secondary hover:text-accent-primary"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to Documents
        </Link>

        {authLoading || loading ? (
          <div className="flex items-center gap-2 rounded-lg border border-border-default bg-surface px-4 py-10 text-body-sm text-tertiary">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Loading document…
          </div>
        ) : !isManage ? (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-border-default bg-surface px-6 py-14 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft">
              <ShieldAlert className="h-6 w-6 text-danger" aria-hidden />
            </span>
            <h1 className="text-h2 text-primary">
              You don&apos;t have permission to view documents.
            </h1>
          </div>
        ) : error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="flex flex-col gap-2">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => void reload()}
                className="inline-flex w-fit items-center gap-1.5 text-body-sm font-medium underline"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden />
                Retry
              </button>
            </div>
          </div>
        ) : detail ? (
          <>
            <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 items-start gap-3">
                <FileTypeIcon fileType={detail.file_type} />
                <div className="min-w-0">
                  <h1 className="text-h1 text-primary">{detail.title}</h1>
                  <p className="mt-1 text-body-sm text-secondary">
                    {detail.filename ?? "—"} · {FILE_TYPE_LABEL[detail.file_type]}
                  </p>
                  <p className="mt-1 text-caption text-tertiary" title={detail.id}>
                    Document ID · {detail.id}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => void reload()}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-border-default bg-surface px-3 text-body-sm font-medium text-primary hover:bg-elevated"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden />
                Refresh
              </button>
            </header>

            {failed ? (
              <div
                role="alert"
                className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-body-sm text-danger"
              >
                <p className="font-semibold">Processing failed</p>
                {pipeline?.error_message ? (
                  <p className="mt-1">{pipeline.error_message}</p>
                ) : (
                  <p className="mt-1 text-danger/90">
                    The current version did not complete successfully. Inspect pipeline stages
                    below for the failure point.
                  </p>
                )}
                {pipeline ? (
                  <p className="mt-2 text-caption">
                    Pipeline run · {pipeline.id.slice(0, 8)}
                    {pipeline.completed_at
                      ? ` · Failed at ${formatFullTimestamp(pipeline.completed_at)}`
                      : ""}
                  </p>
                ) : null}
              </div>
            ) : null}

            <AdminCard headingId="admin-doc-basic" title="Basic information">
              <dl>
                <MetaRow label="Title">{detail.title}</MetaRow>
                <MetaRow label="Filename">{detail.filename ?? "—"}</MetaRow>
                <MetaRow label="File type">
                  {FILE_TYPE_LABEL[detail.file_type]}
                </MetaRow>
                <MetaRow label="Workspace">
                  <Link
                    href={`/admin/workspaces/${detail.workspace_id}`}
                    className="font-medium text-accent-primary hover:underline"
                  >
                    {detail.workspace_name}
                  </Link>
                </MetaRow>
                <MetaRow label="Created">
                  {formatFullTimestamp(detail.created_at)}
                </MetaRow>
                <MetaRow label="Updated">
                  {formatFullTimestamp(detail.updated_at)}
                </MetaRow>
              </dl>
            </AdminCard>

            <AdminCard headingId="admin-doc-version" title="Current version">
              {current ? (
                <dl>
                  <MetaRow label="Version">v{current.version_number}</MetaRow>
                  <MetaRow label="Status">
                    <StatusLine status={current.status} />
                  </MetaRow>
                  <MetaRow label="Size">
                    {formatAdminFileSize(current.file_size_bytes)}
                  </MetaRow>
                  <MetaRow label="Pages">
                    {current.page_count != null ? current.page_count : "—"}
                  </MetaRow>
                  <MetaRow label="Checksum">
                    <code className="break-all text-caption text-secondary">
                      {current.checksum_sha256}
                    </code>
                  </MetaRow>
                  <MetaRow label="Created">
                    {formatFullTimestamp(current.created_at)}
                  </MetaRow>
                </dl>
              ) : (
                <p className="text-body-sm text-tertiary">No current version.</p>
              )}
            </AdminCard>

            <div id="versions">
              <AdminCard headingId="admin-doc-versions" title="Version history">
                {versions.length === 0 ? (
                  <p className="text-body-sm text-tertiary">No versions recorded.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[28rem] border-collapse text-left text-body-sm">
                      <thead>
                        <tr className="border-b border-border-default text-caption font-semibold uppercase tracking-wider text-tertiary">
                          <th scope="col" className="px-2 py-2">
                            Version
                          </th>
                          <th scope="col" className="px-2 py-2">
                            Status
                          </th>
                          <th scope="col" className="px-2 py-2">
                            Size
                          </th>
                          <th scope="col" className="px-2 py-2">
                            Created
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {versions.map((v) => (
                          <tr
                            key={v.id}
                            className="border-b border-border-default/70 last:border-0"
                          >
                            <td className="px-2 py-2 font-medium text-primary">
                              v{v.version_number}
                              {v.is_current ? (
                                <span className="ml-2 text-caption font-normal text-tertiary">
                                  current
                                </span>
                              ) : null}
                            </td>
                            <td className="px-2 py-2">
                              <StatusLine status={v.status} />
                            </td>
                            <td className="px-2 py-2 tabular-nums text-secondary">
                              {formatAdminFileSize(v.file_size_bytes)}
                            </td>
                            <td className="px-2 py-2 text-secondary">
                              {formatFullTimestamp(v.created_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </AdminCard>
            </div>

            <div id="pipeline">
              <AdminCard
                headingId="admin-doc-pipeline"
                title="Pipeline"
                description="Latest pipeline run for the current version."
              >
                {pipeline ? (
                  <div className="flex flex-col gap-4">
                    <dl>
                      <MetaRow label="Status">
                        {PIPELINE_STATUS_LABEL[pipeline.status]}
                      </MetaRow>
                      <MetaRow label="Started">
                        {pipeline.started_at
                          ? formatFullTimestamp(pipeline.started_at)
                          : "—"}
                      </MetaRow>
                      <MetaRow label="Completed">
                        {pipeline.completed_at
                          ? formatFullTimestamp(pipeline.completed_at)
                          : "—"}
                      </MetaRow>
                      <MetaRow label="Duration">
                        {pipeline.started_at && pipeline.completed_at
                          ? formatLatency(
                              Math.max(
                                0,
                                new Date(pipeline.completed_at).getTime() -
                                  new Date(pipeline.started_at).getTime(),
                              ),
                            )
                          : "—"}
                      </MetaRow>
                      <MetaRow label="Retries">{pipeline.retry_count}</MetaRow>
                    </dl>
                    <div>
                      <h3 className="mb-2 text-caption font-semibold uppercase tracking-wider text-tertiary">
                        Processing stages
                      </h3>
                      <PipelineStages stages={pipeline.stages} />
                    </div>
                    <p className="text-caption text-tertiary">
                      For workspace-wide pipeline operations, open the Admin Dashboard pipeline
                      panel for this workspace.
                    </p>
                  </div>
                ) : (
                  <p className="text-body-sm text-tertiary">
                    No pipeline run recorded for the current version.
                  </p>
                )}
              </AdminCard>
            </div>
          </>
        ) : null}
      </div>
    </AdminShell>
  );
}
