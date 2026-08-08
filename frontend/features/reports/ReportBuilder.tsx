/**
 * =============================================================================
 * File: ReportBuilder.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Form to compose report sources and submit async generation (UC8).
 * Responsibilities:
 *   - Title + export_format; tabbed source picker; order_index via up/down
 *   - POST create → show pending; poll via useReportStatusPoll; download / retry
 * Dependencies:
 *   - useReportSources, useReportStatusPoll, report-format, types/reports
 * Public Exports:
 *   - ReportBuilder
 * Database/Table: N/A
 * Related Modules: ReportsView, ReportList
 * Important Notes: Items sent as OpenAPI ReportItemInput only.
 * =============================================================================
 */

"use client";

import {
  ArrowDown,
  ArrowUp,
  Download,
  Loader2,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import {
  EXPORT_FORMAT_OPTIONS,
  reportSourceTypeLabel,
  reportStatusLabel,
} from "@/features/reports/report-format";
import {
  type ReportSourceOption,
  useReportSources,
} from "@/hooks/useReportSources";
import { useReportStatusPoll } from "@/hooks/useReportStatusPoll";
import { cn } from "@/lib/utils";
import type {
  Report,
  ReportCreateRequest,
  ReportExportFormat,
  ReportItemInput,
  ReportSourceType,
} from "@/types/reports";

type SelectedRow = ReportSourceOption & { key: string };

type SourceTab = ReportSourceType;

const TABS: ReadonlyArray<{ id: SourceTab; label: string }> = [
  { id: "summary", label: "Tóm tắt" },
  { id: "extraction", label: "Trích xuất" },
  { id: "comparison", label: "So sánh" },
  { id: "chat_session", label: "Phiên chat" },
];

type Props = {
  workspaceId: string;
  canEdit: boolean;
  submitting: boolean;
  onSubmit: (body: ReportCreateRequest) => Promise<Report | null>;
  onDownload: (reportId: string) => Promise<boolean>;
  onCreated?: (report: Report) => void;
};

function optionKey(opt: Pick<ReportSourceOption, "source_type" | "source_id">): string {
  return `${opt.source_type}:${opt.source_id}`;
}

export function ReportBuilder({
  workspaceId,
  canEdit,
  submitting,
  onSubmit,
  onDownload,
  onCreated,
}: Props) {
  const {
    summaries,
    extractions,
    comparisons,
    chatSessions,
    loading: sourcesLoading,
    error: sourcesError,
    reload: reloadSources,
  } = useReportSources(workspaceId);

  const [title, setTitle] = useState("");
  const [exportFormat, setExportFormat] =
    useState<ReportExportFormat>("pdf");
  const [tab, setTab] = useState<SourceTab>("summary");
  const [selected, setSelected] = useState<SelectedRow[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const { report: polled, polling } = useReportStatusPoll(
    workspaceId,
    activeReportId,
    {
      intervalMs: 2000,
      onUpdate: (row) => onCreated?.(row),
    },
  );

  const catalog = useMemo(() => {
    switch (tab) {
      case "summary":
        return summaries;
      case "extraction":
        return extractions;
      case "comparison":
        return comparisons;
      case "chat_session":
        return chatSessions;
      default:
        return [];
    }
  }, [tab, summaries, extractions, comparisons, chatSessions]);

  const selectedKeys = useMemo(
    () => new Set(selected.map((s) => s.key)),
    [selected],
  );

  function toggleSource(opt: ReportSourceOption) {
    const key = optionKey(opt);
    setSelected((prev) => {
      if (prev.some((s) => s.key === key)) {
        return prev.filter((s) => s.key !== key);
      }
      return [...prev, { ...opt, key }];
    });
    setFormError(null);
  }

  function moveSelected(index: number, delta: number) {
    setSelected((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      const tmp = next[index];
      next[index] = next[target];
      next[target] = tmp;
      return next;
    });
  }

  function removeSelected(key: string) {
    setSelected((prev) => prev.filter((s) => s.key !== key));
  }

  function buildItems(): ReportItemInput[] {
    return selected.map((row, index) => ({
      source_type: row.source_type,
      source_id: row.source_id,
      order_index: index,
    }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canEdit || submitting) return;
    const cleanedTitle = title.trim();
    if (!cleanedTitle) {
      setFormError("Nhập tiêu đề báo cáo.");
      return;
    }
    if (selected.length === 0) {
      setFormError("Chọn ít nhất một nguồn.");
      return;
    }
    setFormError(null);
    const row = await onSubmit({
      title: cleanedTitle,
      export_format: exportFormat,
      items: buildItems(),
    });
    if (row) {
      setActiveReportId(row.id);
      onCreated?.(row);
    }
  }

  async function handleDownload() {
    if (!activeReportId || downloading) return;
    setDownloading(true);
    try {
      await onDownload(activeReportId);
    } finally {
      setDownloading(false);
    }
  }

  function handleRetry() {
    setActiveReportId(null);
    setFormError(null);
  }

  const status = polled?.status ?? (activeReportId ? "pending" : null);
  const showPending = Boolean(activeReportId) && (polling || status === "pending");
  const showReady = status === "ready";
  const showFailed = status === "failed";

  return (
    <section
      aria-labelledby="report-builder-heading"
      className="rounded-lg border border-border-default bg-surface p-4 sm:p-5"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 id="report-builder-heading" className="text-h3 text-primary">
            Tạo báo cáo
          </h2>
          <p className="mt-1 text-body-sm text-secondary">
            Ghép tóm tắt, trích xuất, so sánh và phiên chat thành một file xuất.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void reloadSources()}
          disabled={sourcesLoading}
          className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border-default px-2.5 text-caption font-medium text-secondary hover:bg-elevated disabled:opacity-50"
        >
          <RefreshCw
            className={cn("h-3.5 w-3.5", sourcesLoading && "animate-spin")}
            aria-hidden
          />
          Nguồn
        </button>
      </div>

      {sourcesError ? (
        <p role="alert" className="mb-3 text-body-sm text-danger">
          {sourcesError}
        </p>
      ) : null}

      <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-caption font-medium text-secondary">Tiêu đề</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={!canEdit || submitting || showPending}
            placeholder="Ví dụ: Báo cáo tuần 12"
            className={cn(
              "h-10 rounded-md border border-border-default bg-elevated px-3 text-body-sm text-primary",
              "placeholder:text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
              "disabled:opacity-60",
            )}
          />
        </label>

        <fieldset className="flex flex-col gap-2">
          <legend className="text-caption font-medium text-secondary">
            Định dạng xuất
          </legend>
          <div className="flex flex-wrap gap-3">
            {EXPORT_FORMAT_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={cn(
                  "inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-body-sm",
                  exportFormat === opt.value
                    ? "border-accent-primary/40 bg-accent-primary/5 text-primary"
                    : "border-border-default text-secondary hover:bg-elevated",
                  (!canEdit || submitting || showPending) &&
                    "cursor-not-allowed opacity-60",
                )}
              >
                <input
                  type="radio"
                  name="export_format"
                  value={opt.value}
                  checked={exportFormat === opt.value}
                  disabled={!canEdit || submitting || showPending}
                  onChange={() => setExportFormat(opt.value)}
                  className="accent-[var(--color-accent-primary,theme(colors.blue.600))]"
                />
                {opt.label}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="min-w-0">
            <p className="mb-2 text-caption font-medium text-secondary">
              Chọn nguồn
            </p>
            <div
              role="tablist"
              aria-label="Loại nguồn"
              className="mb-2 flex flex-wrap gap-1"
            >
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => setTab(t.id)}
                  className={cn(
                    "rounded-md px-2.5 py-1.5 text-caption font-medium transition-colors",
                    tab === t.id
                      ? "bg-accent-primary-soft text-accent-primary"
                      : "text-secondary hover:bg-elevated",
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div
              role="tabpanel"
              className="max-h-56 overflow-y-auto rounded-md border border-border-default"
            >
              {sourcesLoading ? (
                <p className="px-3 py-4 text-body-sm text-tertiary">
                  Đang tải nguồn…
                </p>
              ) : catalog.length === 0 ? (
                <p className="px-3 py-4 text-body-sm text-tertiary">
                  Chưa có {reportSourceTypeLabel(tab).toLowerCase()} hoàn thành.
                </p>
              ) : (
                <ul className="divide-y divide-border-default">
                  {catalog.map((opt) => {
                    const key = optionKey(opt);
                    const checked = selectedKeys.has(key);
                    return (
                      <li key={key}>
                        <label
                          className={cn(
                            "flex cursor-pointer items-start gap-2.5 px-3 py-2.5 text-body-sm hover:bg-elevated",
                            (!canEdit || showPending) &&
                              "cursor-not-allowed opacity-60",
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={!canEdit || showPending}
                            onChange={() => toggleSource(opt)}
                            className="mt-0.5"
                          />
                          <span className="min-w-0">
                            <span className="block truncate font-medium text-primary">
                              {opt.label}
                            </span>
                            <span className="block text-caption text-tertiary">
                              {reportSourceTypeLabel(opt.source_type)}
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>

          <div className="min-w-0">
            <p className="mb-2 text-caption font-medium text-secondary">
              Thứ tự trong báo cáo ({selected.length})
            </p>
            {selected.length === 0 ? (
              <p className="rounded-md border border-dashed border-border-default px-3 py-6 text-center text-body-sm text-tertiary">
                Chọn nguồn bên trái — dùng mũi tên để sắp xếp.
              </p>
            ) : (
              <ul className="flex max-h-56 flex-col gap-1.5 overflow-y-auto">
                {selected.map((row, index) => (
                  <li
                    key={row.key}
                    className="flex items-center gap-1.5 rounded-md border border-border-default bg-elevated/40 px-2 py-1.5"
                  >
                    <span className="w-5 shrink-0 text-center text-caption text-tertiary">
                      {index + 1}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-body-sm text-primary">
                      {row.label}
                    </span>
                    <button
                      type="button"
                      aria-label="Đưa lên"
                      disabled={index === 0 || showPending}
                      onClick={() => moveSelected(index, -1)}
                      className="flex h-7 w-7 items-center justify-center rounded text-secondary hover:bg-elevated disabled:opacity-40"
                    >
                      <ArrowUp className="h-3.5 w-3.5" aria-hidden />
                    </button>
                    <button
                      type="button"
                      aria-label="Đưa xuống"
                      disabled={index === selected.length - 1 || showPending}
                      onClick={() => moveSelected(index, 1)}
                      className="flex h-7 w-7 items-center justify-center rounded text-secondary hover:bg-elevated disabled:opacity-40"
                    >
                      <ArrowDown className="h-3.5 w-3.5" aria-hidden />
                    </button>
                    <button
                      type="button"
                      aria-label="Bỏ chọn"
                      disabled={showPending}
                      onClick={() => removeSelected(row.key)}
                      className="flex h-7 w-7 items-center justify-center rounded text-tertiary hover:bg-elevated hover:text-danger disabled:opacity-40"
                    >
                      <X className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {formError ? (
          <p role="alert" className="text-body-sm text-danger">
            {formError}
          </p>
        ) : null}

        {showPending ? (
          <div
            role="status"
            className="flex items-center gap-2 rounded-md border border-warning/30 bg-warning/10 px-3 py-2.5 text-body-sm text-primary"
          >
            <Loader2 className="h-4 w-4 animate-spin text-warning" aria-hidden />
            <span>
              Đang xử lý báo cáo
              {polled ? ` — ${reportStatusLabel(polled.status)}` : "…"}
            </span>
          </div>
        ) : null}

        {showReady ? (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2.5">
            <span className="text-body-sm text-primary">
              Báo cáo sẵn sàng tải xuống.
            </span>
            <button
              type="button"
              onClick={() => void handleDownload()}
              disabled={downloading}
              className="inline-flex h-9 items-center gap-1.5 rounded-md bg-accent-primary px-3 text-body-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {downloading ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Download className="h-4 w-4" aria-hidden />
              )}
              Tải xuống
            </button>
            <button
              type="button"
              onClick={handleRetry}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border-default px-3 text-body-sm font-medium text-secondary hover:bg-elevated"
            >
              Tạo báo cáo khác
            </button>
          </div>
        ) : null}

        {showFailed ? (
          <div
            role="alert"
            className="flex flex-wrap items-center gap-2 rounded-md border border-danger/30 bg-danger-soft px-3 py-2.5"
          >
            <span className="text-body-sm text-danger">
              Sinh báo cáo thất bại. Bạn có thể thử tạo lại.
            </span>
            <button
              type="button"
              onClick={handleRetry}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border-default bg-surface px-3 text-body-sm font-medium text-secondary hover:bg-elevated"
            >
              Thử tạo lại
            </button>
          </div>
        ) : null}

        {!showReady && !showFailed ? (
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!canEdit || submitting || showPending}
              className={cn(
                "inline-flex h-10 items-center justify-center gap-2 rounded-md bg-accent-primary px-4",
                "text-body-sm font-medium text-white hover:opacity-90",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {submitting || showPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Plus className="h-4 w-4" aria-hidden />
              )}
              {submitting || showPending ? "Đang tạo…" : "Tạo báo cáo"}
            </button>
          </div>
        ) : null}

        {!canEdit ? (
          <p className="text-caption text-tertiary">
            Bạn cần quyền Editor trở lên để tạo báo cáo.
          </p>
        ) : null}
      </form>
    </section>
  );
}
