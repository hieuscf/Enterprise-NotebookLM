/**
 * =============================================================================
 * File: SummarySection.tsx
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: Document-detail AI Summary section — styles, language, reuse, poll.
 * Responsibilities:
 *   - Reuse current-version completed Summary (no auto POST on style switch)
 *   - Language switch requests generation when no match; hide stale language content
 *   - Explicit create / regenerate; poll processing; copy action
 * Dependencies:
 *   - useDocumentSummaries, summary-format, SummaryStyleSelector,
 *     SummaryLanguageSelector, SummaryContent, SummaryHistory
 * Public Exports:
 *   - SummarySection
 * Database/Table: N/A
 * Related Modules: features/documents/DocumentDetailView,
 *   features/summaries/SummariesView
 * Important Notes: Never POSTs on style switch when a current completed Summary
 *   exists. Language selection filters by target_language (cache-key dimension).
 * =============================================================================
 */

"use client";

import { AlertCircle, Copy, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { SummaryContent } from "@/features/summaries/SummaryContent";
import { SummaryHistory } from "@/features/summaries/SummaryHistory";
import { SummaryLanguageSelector } from "@/features/summaries/SummaryLanguageSelector";
import { SummaryStyleSelector } from "@/features/summaries/SummaryStyleSelector";
import {
  buildCopyText,
  getCurrentSummary,
  getFailedSummary,
  getProcessingSummary,
  isOldVersion,
  styleLabel,
} from "@/features/summaries/summary-format";
import { useDocumentSummaries } from "@/hooks/useDocumentSummaries";
import { cn } from "@/lib/utils";
import type { Summary, SummaryStyle, TargetLanguage } from "@/types/summaries";

type Props = {
  workspaceId: string;
  documentId: string;
  currentVersionId: string | null;
  canEdit: boolean;
  onCopied?: () => void;
  onCopyFailed?: () => void;
  onCreateError?: (message: string) => void;
};

export function SummarySection({
  workspaceId,
  documentId,
  currentVersionId,
  canEdit,
  onCopied,
  onCopyFailed,
  onCreateError,
}: Props) {
  const { summaries, loading, error, creating, createSummary, reload } =
    useDocumentSummaries(workspaceId, documentId);

  const [selectedStyle, setSelectedStyle] = useState<SummaryStyle>("short");
  const [selectedLanguage, setSelectedLanguage] = useState<TargetLanguage>("vi");
  const [historySelection, setHistorySelection] = useState<Summary | null>(null);
  const [showOldHint, setShowOldHint] = useState(false);
  const [awaitingLanguage, setAwaitingLanguage] = useState(false);

  /** Monotonic request id so stale create responses never drive UI after language flips. */
  const requestSeqRef = useRef(0);
  const selectedLanguageRef = useRef(selectedLanguage);
  const prevLanguageRef = useRef(selectedLanguage);
  selectedLanguageRef.current = selectedLanguage;

  const currentCompleted = useMemo(
    () =>
      getCurrentSummary(summaries, currentVersionId, selectedStyle, selectedLanguage),
    [summaries, currentVersionId, selectedStyle, selectedLanguage],
  );
  const processing = useMemo(
    () =>
      getProcessingSummary(
        summaries,
        currentVersionId,
        selectedStyle,
        selectedLanguage,
      ),
    [summaries, currentVersionId, selectedStyle, selectedLanguage],
  );
  const failed = useMemo(
    () =>
      getFailedSummary(summaries, currentVersionId, selectedStyle, selectedLanguage),
    [summaries, currentVersionId, selectedStyle, selectedLanguage],
  );

  const generatedLanguage: TargetLanguage | null =
    currentCompleted?.target_language ??
    processing?.target_language ??
    (failed?.target_language ?? null);

  const oldForStyle = useMemo(() => {
    if (currentCompleted || !currentVersionId) return null;
    const olds = summaries.filter(
      (s) =>
        s.status === "completed" &&
        s.style === selectedStyle &&
        (s.target_language ?? "vi") === selectedLanguage &&
        s.source_version_id !== currentVersionId,
    );
    if (olds.length === 0) return null;
    return [...olds].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )[0];
  }, [summaries, currentVersionId, currentCompleted, selectedStyle, selectedLanguage]);

  // Clear history override when style/language changes or a newer current summary appears.
  useEffect(() => {
    setHistorySelection(null);
    setShowOldHint(Boolean(oldForStyle) && !currentCompleted);
  }, [selectedStyle, selectedLanguage, currentCompleted, oldForStyle]);

  useEffect(() => {
    if (currentCompleted || processing || failed) {
      setAwaitingLanguage(false);
    }
  }, [currentCompleted, processing, failed]);

  // Auto-create only when the user changes output language (not on mount / style switch).
  useEffect(() => {
    const prev = prevLanguageRef.current;
    if (prev === selectedLanguage) return;
    prevLanguageRef.current = selectedLanguage;

    if (!canEdit || !currentVersionId || loading) return;
    if (currentCompleted || processing) {
      setAwaitingLanguage(false);
      return;
    }

    setAwaitingLanguage(true);
    const seq = ++requestSeqRef.current;
    const lang = selectedLanguage;
    const style = selectedStyle;
    void (async () => {
      const row = await createSummary(style, lang);
      if (seq !== requestSeqRef.current) return;
      if (selectedLanguageRef.current !== lang) return;
      if (!row) {
        setAwaitingLanguage(false);
        onCreateError?.(
          "Unable to generate summary in the selected language. Please try again.",
        );
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLanguage]);

  const displayed: Summary | null =
    historySelection &&
    (historySelection.target_language ?? "vi") === selectedLanguage
      ? historySelection
      : processing ??
        currentCompleted ??
        (failed && !currentCompleted ? failed : null);

  const busy = creating || Boolean(processing) || awaitingLanguage;

  async function handleCreate() {
    if (!canEdit || busy) return;
    const seq = ++requestSeqRef.current;
    const lang = selectedLanguage;
    const row = await createSummary(selectedStyle, lang);
    if (seq !== requestSeqRef.current || selectedLanguageRef.current !== lang) {
      return;
    }
    if (!row && onCreateError) {
      onCreateError(
        "Unable to generate summary in the selected language. Please try again.",
      );
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

  function handleLanguageChange(next: TargetLanguage) {
    if (next === selectedLanguage) return;
    requestSeqRef.current += 1;
    setAwaitingLanguage(true);
    setSelectedLanguage(next);
    setHistorySelection(null);
  }

  const showGenerating = busy && (!displayed || displayed.status === "processing");
  const showEmpty =
    !busy && !currentCompleted && !failed && !historySelection;
  const showFailed =
    !busy && failed && !currentCompleted && !historySelection;
  const showCompleted = displayed && displayed.status === "completed" && !busy;

  return (
    <section className="flex flex-col gap-4" aria-label="Tóm tắt tài liệu">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-h3 text-primary">Tóm tắt</h2>
          <p className="mt-0.5 text-body-sm text-secondary">
            Chọn kiểu tóm tắt và ngôn ngữ đầu ra. Kết quả đã có cho phiên bản hiện tại
            sẽ được dùng lại (không gọi AI lại).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <SummaryLanguageSelector
            value={selectedLanguage}
            onChange={handleLanguageChange}
            disabled={creating && !processing}
          />
          {canEdit && currentCompleted && !busy ? (
            <button
              type="button"
              onClick={() => void handleCreate()}
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded-md border border-border-default px-3.5",
                "text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary",
              )}
              aria-label={`Tạo lại tóm tắt ${styleLabel(selectedStyle)}`}
            >
              <RefreshCw className="h-4 w-4" aria-hidden />
              Tạo lại
            </button>
          ) : null}
        </div>
      </div>

      <SummaryStyleSelector
        value={selectedStyle}
        onChange={setSelectedStyle}
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
          <span className="sr-only">Đang tải lịch sử tóm tắt</span>
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
        {showGenerating ? (
          <div
            className="flex items-center gap-3 text-body-sm text-secondary"
            aria-live="polite"
            aria-busy="true"
          >
            <Loader2 className="h-4 w-4 animate-spin text-warning" aria-hidden />
            <div>
              <p className="font-medium text-primary">Generating summary…</p>
              <p className="text-caption text-tertiary">
                Output language:{" "}
                {selectedLanguage === "en" ? "English" : "Tiếng Việt"}
                {generatedLanguage && generatedLanguage !== selectedLanguage
                  ? ` (previous: ${generatedLanguage})`
                  : ""}
              </p>
            </div>
          </div>
        ) : null}

        {showEmpty ? (
          <div className="flex flex-col items-start gap-3 py-2">
            <p className="text-body-sm text-secondary">
              Chưa có tóm tắt cho phiên bản này
              {selectedStyle ? ` (${styleLabel(selectedStyle)})` : ""}.
            </p>
            {showOldHint && oldForStyle ? (
              <p className="text-caption text-tertiary">
                Có kết quả cũ hơn ({styleLabel(oldForStyle.style)}) — chọn trong lịch sử
                để xem, hoặc tạo mới cho phiên bản hiện tại.
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
                Tạo tóm tắt
              </button>
            ) : (
              <p className="text-caption text-tertiary">
                Chỉ biên tập viên hoặc quản trị viên mới tạo được tóm tắt mới.
              </p>
            )}
          </div>
        ) : null}

        {showFailed ? (
          <div className="flex flex-col gap-3" role="alert">
            <p className="flex items-center gap-2 text-body-sm text-danger">
              <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
              Unable to generate summary in the selected language. Please try again.
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

        {showCompleted && displayed ? (
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
            <SummaryContent summary={displayed} />
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
                disabled
                title="Xuất file sẽ có ở module Báo cáo (FR9)"
                className="inline-flex h-8 cursor-not-allowed items-center rounded-md border border-border-default px-3 text-caption text-tertiary opacity-60"
              >
                Xuất
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-body-sm font-semibold text-primary">Lịch sử tóm tắt</h3>
        <SummaryHistory
          summaries={summaries}
          currentVersionId={currentVersionId}
          selectedId={displayed?.id ?? null}
          onSelect={(s) => {
            if (s.status === "completed") {
              setSelectedLanguage(s.target_language ?? "vi");
              setHistorySelection(s);
            }
          }}
        />
      </div>
    </section>
  );
}
