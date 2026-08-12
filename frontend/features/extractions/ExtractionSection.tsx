/**
 * =============================================================================
 * File: ExtractionSection.tsx
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Document-detail Information Extraction section (FR7 Part 6).
 * Responsibilities:
 *   - Reuse current-version completed Extraction (no auto POST)
 *   - Explicit create / regenerate; poll processing; copy + CSV/JSON export
 * Dependencies:
 *   - useDocumentExtractions, extraction-format, ExtractionControls,
 *     ExtractionContent, ExtractionHistory, lib/download
 * Public Exports:
 *   - ExtractionSection
 * Database/Table: N/A
 * Related Modules: features/documents/DocumentDetailView,
 *   features/extractions/ExtractionsView
 * Important Notes: Mirrors SummarySection UX. Never POSTs on type/format switch.
 *   Visual timeline deferred — table/JSON only.
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  Copy,
  Download,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ExtractionContent } from "@/features/extractions/ExtractionContent";
import { ExtractionControls } from "@/features/extractions/ExtractionControls";
import { ExtractionHistory } from "@/features/extractions/ExtractionHistory";
import {
  buildCopyText,
  buildCsvFromExtraction,
  buildExportFilename,
  buildJsonExport,
  formatLabel,
  getCurrentExtraction,
  getFailedExtraction,
  getProcessingExtraction,
  isOldVersion,
  typeLabel,
} from "@/features/extractions/extraction-format";
import { useDocumentExtractions } from "@/hooks/useDocumentExtractions";
import { downloadTextFile } from "@/lib/download";
import { cn } from "@/lib/utils";
import type {
  Extraction,
  ExtractionOutputFormat,
  ExtractionType,
} from "@/types/extractions";

type Props = {
  workspaceId: string;
  documentId: string;
  currentVersionId: string | null;
  canEdit: boolean;
  onCopied?: () => void;
  onCopyFailed?: () => void;
  onExportError?: (message: string) => void;
  onCreateError?: (message: string) => void;
};

export function ExtractionSection({
  workspaceId,
  documentId,
  currentVersionId,
  canEdit,
  onCopied,
  onCopyFailed,
  onExportError,
  onCreateError,
}: Props) {
  const { extractions, loading, error, creating, createExtraction, reload } =
    useDocumentExtractions(workspaceId, documentId);

  const [extractionType, setExtractionType] = useState<ExtractionType>("table");
  const [outputFormat, setOutputFormat] = useState<ExtractionOutputFormat>("json");
  const [historySelection, setHistorySelection] = useState<Extraction | null>(null);
  const [showOldHint, setShowOldHint] = useState(false);

  const currentCompleted = useMemo(
    () =>
      getCurrentExtraction(
        extractions,
        currentVersionId,
        extractionType,
        outputFormat,
      ),
    [extractions, currentVersionId, extractionType, outputFormat],
  );
  const processing = useMemo(
    () =>
      getProcessingExtraction(
        extractions,
        currentVersionId,
        extractionType,
        outputFormat,
      ),
    [extractions, currentVersionId, extractionType, outputFormat],
  );
  const failed = useMemo(
    () =>
      getFailedExtraction(
        extractions,
        currentVersionId,
        extractionType,
        outputFormat,
      ),
    [extractions, currentVersionId, extractionType, outputFormat],
  );

  const oldForSelection = useMemo(() => {
    if (currentCompleted || !currentVersionId) return null;
    const olds = extractions.filter(
      (e) =>
        e.status === "completed" &&
        e.extraction_type === extractionType &&
        e.output_format === outputFormat &&
        e.source_version_id !== currentVersionId,
    );
    if (olds.length === 0) return null;
    return [...olds].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )[0];
  }, [
    extractions,
    currentVersionId,
    currentCompleted,
    extractionType,
    outputFormat,
  ]);

  useEffect(() => {
    setHistorySelection(null);
    setShowOldHint(Boolean(oldForSelection) && !currentCompleted);
  }, [extractionType, outputFormat, currentCompleted, oldForSelection, currentVersionId]);

  const displayed: Extraction | null =
    historySelection ??
    processing ??
    currentCompleted ??
    (failed && !currentCompleted ? failed : null);

  const busy = creating || Boolean(processing);
  const canExport =
    Boolean(displayed) &&
    displayed?.status === "completed" &&
    displayed.result != null &&
    !busy;

  async function handleCreate() {
    if (!canEdit || busy) return;
    const row = await createExtraction(extractionType, outputFormat);
    if (!row && onCreateError) {
      onCreateError("Không tạo được trích xuất.");
    }
    setHistorySelection(null);
  }

  async function handleCopy() {
    if (!displayed || displayed.status !== "completed") return;
    const text = buildCopyText(displayed);
    if (!text) {
      onCopyFailed?.();
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      onCopied?.();
    } catch {
      onCopyFailed?.();
    }
  }

  function handleExport() {
    if (!displayed || displayed.status !== "completed") return;
    try {
      if (displayed.output_format === "table") {
        const csv = buildCsvFromExtraction(displayed);
        if (!csv) {
          onExportError?.("Không có dữ liệu bảng để xuất CSV.");
          return;
        }
        downloadTextFile(
          csv,
          buildExportFilename(documentId, displayed.extraction_type, "csv"),
          "text/csv;charset=utf-8",
        );
        return;
      }
      const json = buildJsonExport(displayed);
      if (!json) {
        onExportError?.("Không có dữ liệu JSON để xuất.");
        return;
      }
      downloadTextFile(
        json,
        buildExportFilename(documentId, displayed.extraction_type, "json"),
        "application/json;charset=utf-8",
      );
    } catch {
      onExportError?.("Không xuất được file.");
    }
  }

  return (
    <section className="flex flex-col gap-4" aria-label="Trích xuất thông tin">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-h3 text-primary">Trích xuất thông tin</h2>
          <p className="mt-0.5 text-body-sm text-secondary">
            Chọn loại và định dạng. Kết quả đã có cho phiên bản hiện tại sẽ được dùng lại
            (không gọi AI lại).
          </p>
        </div>
        {canEdit && currentCompleted && !busy ? (
          <button
            type="button"
            onClick={() => void handleCreate()}
            className={cn(
              "inline-flex h-9 items-center gap-2 rounded-md border border-border-default px-3.5",
              "text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary",
            )}
            aria-label={`Tạo lại trích xuất ${typeLabel(extractionType)} ${formatLabel(outputFormat)}`}
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
            Tạo lại
          </button>
        ) : null}
      </div>

      <ExtractionControls
        extractionType={extractionType}
        outputFormat={outputFormat}
        onTypeChange={setExtractionType}
        onFormatChange={setOutputFormat}
        disabled={busy}
      />

      {loading ? (
        <div
          className="animate-pulse space-y-2 rounded-lg border border-border-default bg-surface p-4"
          aria-busy="true"
          aria-live="polite"
        >
          <div className="h-4 w-1/3 rounded bg-elevated" />
          <div className="h-3 w-full rounded bg-elevated" />
          <div className="h-3 w-5/6 rounded bg-elevated" />
          <span className="sr-only">Đang tải lịch sử trích xuất</span>
        </div>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
          {error}
          <button
            type="button"
            onClick={() => void reload()}
            className="ml-auto text-body-sm font-medium underline"
          >
            Thử lại
          </button>
        </p>
      ) : null}

      <div className="rounded-lg border border-border-default bg-surface p-4 shadow-sm">
        {busy && (!displayed || displayed.status === "processing") ? (
          <div
            className="flex items-center gap-3 text-body-sm text-secondary"
            aria-live="polite"
            aria-busy="true"
          >
            <Loader2 className="h-4 w-4 animate-spin text-warning" aria-hidden />
            <div>
              <p className="font-medium text-primary">Đang trích xuất thông tin…</p>
              <p className="text-caption text-tertiary">
                Bạn có thể tiếp tục đọc tài liệu trong lúc chờ.
              </p>
            </div>
          </div>
        ) : null}

        {!busy && !currentCompleted && !failed && !historySelection ? (
          <div className="flex flex-col items-start gap-3 py-2">
            <p className="text-body-sm text-secondary">
              Chưa có kết quả trích xuất cho phiên bản này ({typeLabel(extractionType)} ·{" "}
              {formatLabel(outputFormat)}).
            </p>
            {showOldHint && oldForSelection ? (
              <p className="text-caption text-tertiary">
                Có kết quả cũ hơn — chọn trong lịch sử để xem, hoặc tạo mới cho phiên bản
                hiện tại.
              </p>
            ) : null}
            {canEdit ? (
              <button
                type="button"
                disabled={busy || !currentVersionId}
                onClick={() => void handleCreate()}
                className={cn(
                  "inline-flex h-9 items-center gap-2 rounded-md bg-accent-primary px-3.5",
                  "text-body-sm font-medium text-white hover:bg-accent-primary-hover",
                  "disabled:cursor-not-allowed disabled:opacity-60",
                )}
              >
                <Sparkles className="h-4 w-4" aria-hidden />
                Tạo trích xuất
              </button>
            ) : (
              <p className="text-caption text-tertiary">
                Chỉ editor/admin mới tạo được trích xuất mới.
              </p>
            )}
          </div>
        ) : null}

        {!busy && failed && !currentCompleted && !historySelection ? (
          <div className="flex flex-col gap-3" role="alert">
            <p className="flex items-center gap-2 text-body-sm text-danger">
              <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
              Không thể tạo trích xuất.
            </p>
            {canEdit ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void handleCreate()}
                className={cn(
                  "inline-flex h-9 w-fit items-center gap-2 rounded-md border border-border-default px-3.5",
                  "text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary",
                )}
              >
                <RefreshCw className="h-4 w-4" aria-hidden />
                Thử lại
              </button>
            ) : null}
          </div>
        ) : null}

        {displayed && displayed.status === "completed" ? (
          <div className="flex flex-col gap-3">
            {isOldVersion(displayed, currentVersionId) ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-elevated px-2.5 py-1 text-caption text-secondary">
                  Dựa trên phiên bản cũ
                </span>
                {currentCompleted ? (
                  <button
                    type="button"
                    className="text-caption font-medium text-accent-primary hover:underline"
                    onClick={() => setHistorySelection(null)}
                  >
                    Hiển thị phiên bản hiện tại
                  </button>
                ) : null}
              </div>
            ) : null}
            <ExtractionContent extraction={displayed} />
            <div className="flex flex-wrap gap-2 border-t border-border-default pt-3">
              <button
                type="button"
                onClick={() => void handleCopy()}
                className={cn(
                  "inline-flex h-8 items-center gap-1.5 rounded-md border border-border-default px-3",
                  "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
                )}
              >
                <Copy className="h-3.5 w-3.5" aria-hidden />
                Sao chép
              </button>
              <button
                type="button"
                disabled={!canExport}
                onClick={handleExport}
                aria-label={
                  displayed.output_format === "table"
                    ? "Xuất CSV"
                    : "Xuất JSON"
                }
                className={cn(
                  "inline-flex h-8 items-center gap-1.5 rounded-md border border-border-default px-3",
                  "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
                  !canExport && "cursor-not-allowed opacity-60",
                )}
              >
                <Download className="h-3.5 w-3.5" aria-hidden />
                {displayed.output_format === "table" ? "Xuất CSV" : "Xuất JSON"}
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-body-sm font-semibold text-primary">Lịch sử trích xuất</h3>
        <ExtractionHistory
          extractions={extractions}
          currentVersionId={currentVersionId}
          selectedId={displayed?.id ?? null}
          onSelect={(e) => {
            if (e.status === "completed") setHistorySelection(e);
          }}
        />
      </div>
    </section>
  );
}
