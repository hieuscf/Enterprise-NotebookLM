/**
 * =============================================================================
 * File: ClauseComparisonView.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TASK-CMP-18 focused side-by-side clause comparison workspace.
 * Responsibilities:
 *   - Full original V1/V2 text; backend exact diffs, risk, AI, evidence
 *   - Previous/Next within the active filter list; Escape to close
 * Dependencies:
 *   - clause-view helpers, comparison-badges, document viewer deep-links
 * Public Exports:
 *   - ClauseComparisonView
 * Database/Table: N/A
 * Related Modules: ComparisonSummaryView, document viewer
 * Important Notes: Backend remains source of truth. Source text is immutable.
 *   Do not put clause body into URLs. No frontend diff/risk engine.
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import {
  EvidenceStateBadge,
  RiskBadge,
  StatusBadge,
} from "@/features/comparisons/comparison-badges";
import {
  absenceMessage,
  columnHeading,
  filterLabel,
  highlightSegments,
  mappingConfidenceLabel,
  positionLabel,
  shouldEmphasizeDiff,
  shouldShowAiAnalysis,
  unchangedCaption,
  userFacingRules,
  valueTypeLabel,
  versionMapping,
  type ClauseNav,
  type HighlightSegment,
} from "@/features/comparisons/clause-view";
import {
  clauseRiskLevel,
  displayClauseId,
  evidenceForSide,
  evidenceState,
  evidenceStateLabel,
  evidenceViewerHref,
  explanationText,
  formatExactDifference,
  riskLevelHelp,
  type ClauseFilter,
} from "@/features/comparisons/comparison-summary";
import { cn } from "@/lib/utils";
import type {
  ContractClauseResult,
  ContractComparisonReport,
  ContractEvidenceRef,
  DocumentMeta,
} from "@/types/comparisons";

type Props = {
  open: boolean;
  workspaceId: string;
  report: ContractComparisonReport;
  clause: ContractClauseResult | null;
  nav: ClauseNav;
  filter: ClauseFilter;
  loading?: boolean;
  error?: string | null;
  documentMeta?: Record<string, DocumentMeta>;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  onRetry?: () => void;
};

export function ClauseComparisonView({
  open,
  workspaceId,
  report,
  clause,
  nav,
  filter,
  loading = false,
  error = null,
  documentMeta = {},
  onClose,
  onPrev,
  onNext,
  onRetry,
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [mobilePane, setMobilePane] = useState<"v1" | "v2">("v1");

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "ArrowLeft" && nav.prevId) {
        event.preventDefault();
        onPrev();
      }
      if (event.key === "ArrowRight" && nav.nextId) {
        event.preventDefault();
        onNext();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose, onPrev, onNext, nav.prevId, nav.nextId]);

  useEffect(() => {
    setMobilePane("v1");
  }, [clause?.clause_id]);

  if (!open) return null;

  const v1Doc = report.metadata?.document_v1;
  const v2Doc = report.metadata?.document_v2;
  const v1Title =
    documentMeta[v1Doc?.document_id ?? ""]?.title ?? v1Doc?.title ?? "V1";
  const v2Title =
    documentMeta[v2Doc?.document_id ?? ""]?.title ?? v2Doc?.title ?? "V2";

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center sm:p-4">
      <button
        type="button"
        aria-label="Đóng đối chiếu điều khoản"
        className="absolute inset-0 bg-primary/40"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 flex h-full w-full max-w-6xl flex-col overflow-hidden border-border-default bg-surface shadow-lg sm:rounded-lg sm:border"
      >
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border-default px-4 py-3">
          <div className="min-w-0">
            <p className="text-caption font-medium text-accent-primary">
              Đối chiếu điều khoản
            </p>
            <p className="text-caption text-tertiary">
              {positionLabel(nav, filterLabel(filter))}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={onPrev}
              disabled={!nav.prevId}
              className={navButtonClass}
              aria-label="Điều khoản trước trong bộ lọc hiện tại"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden />
              Trước
            </button>
            <button
              type="button"
              onClick={onNext}
              disabled={!nav.nextId}
              className={navButtonClass}
              aria-label="Điều khoản tiếp theo trong bộ lọc hiện tại"
            >
              Sau
              <ChevronRight className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              ref={closeRef}
              onClick={onClose}
              className={navButtonClass}
              aria-label="Đóng"
            >
              <X className="h-4 w-4" aria-hidden />
              Đóng
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {loading ? <LoadingState /> : null}
          {!loading && error ? (
            <ErrorState message={error} onRetry={onRetry} onBack={onClose} />
          ) : null}
          {!loading && !error && !clause ? (
            <ErrorState
              message="Không tải được đối chiếu điều khoản này."
              onRetry={onRetry}
              onBack={onClose}
            />
          ) : null}
          {!loading && !error && clause ? (
            <ClauseWorkspace
              titleId={titleId}
              clause={clause}
              workspaceId={workspaceId}
              report={report}
              v1Title={v1Title}
              v2Title={v2Title}
              mobilePane={mobilePane}
              onMobilePane={setMobilePane}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

const navButtonClass = cn(
  "inline-flex h-9 items-center gap-1 rounded-md border border-border-default px-2.5",
  "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
  "disabled:cursor-not-allowed disabled:opacity-40",
);

function LoadingState() {
  return (
    <div role="status" className="flex items-center gap-2 py-16 text-body-sm text-secondary">
      <Loader2 className="h-4 w-4 animate-spin text-accent-primary" aria-hidden />
      Đang tải đối chiếu điều khoản…
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
  onBack,
}: {
  message: string;
  onRetry?: () => void;
  onBack: () => void;
}) {
  return (
    <div role="alert" className="flex flex-col gap-3 py-10">
      <div className="flex items-start gap-2 text-body-sm text-danger">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <p>{message}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {onRetry ? (
          <button type="button" onClick={onRetry} className={navButtonClass}>
            Thử lại
          </button>
        ) : null}
        <button type="button" onClick={onBack} className={navButtonClass}>
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Quay lại so sánh
        </button>
      </div>
    </div>
  );
}

function ClauseWorkspace({
  titleId,
  clause,
  workspaceId,
  report,
  v1Title,
  v2Title,
  mobilePane,
  onMobilePane,
}: {
  titleId: string;
  clause: ContractClauseResult;
  workspaceId: string;
  report: ContractComparisonReport;
  v1Title: string;
  v2Title: string;
  mobilePane: "v1" | "v2";
  onMobilePane: (pane: "v1" | "v2") => void;
}) {
  const status = String(clause.status).toUpperCase();
  const risk = clauseRiskLevel(clause);
  const mapping = versionMapping(clause);
  const analysis = explanationText(clause);
  const diffs = clause.exact_differences ?? [];
  const evState = evidenceState(clause);
  const confidence = mappingConfidenceLabel(clause.mapping_confidence);
  const rules = userFacingRules(clause.risk?.triggered_rules ?? null);
  const category = clause.risk?.risk_category ? String(clause.risk.risk_category) : null;
  const showDiff = shouldEmphasizeDiff(status);
  const v1Doc = report.metadata?.document_v1;
  const v2Doc = report.metadata?.document_v2;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 border-b border-border-default pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id={titleId} className="text-h3 text-primary">
              Điều {displayClauseId(clause.clause_id)}
            </h2>
            {category ? (
              <p className="mt-1 text-body-sm text-secondary">{category}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <StatusBadge status={status} />
            <RiskBadge level={risk} />
            <EvidenceStateBadge state={evState} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-body-sm text-secondary">
          <span>V1 · Điều {mapping.v1Label}</span>
          {mapping.renumbered ? (
            <span className="text-tertiary" aria-hidden>
              ↕
            </span>
          ) : (
            <ArrowRight className="h-3.5 w-3.5 text-tertiary" aria-hidden />
          )}
          <span>V2 · Điều {mapping.v2Label}</span>
        </div>
        <dl className="flex flex-wrap gap-x-4 gap-y-1 text-caption text-tertiary">
          {confidence ? (
            <>
              <dt>Độ tin cậy ánh xạ</dt>
              <dd className="text-secondary">{confidence}</dd>
            </>
          ) : null}
          <dt>Xác minh</dt>
          <dd className="text-secondary">{evidenceStateLabel(evState)}</dd>
        </dl>
        {status === "UNCHANGED" ? (
          <p className="text-body-sm text-secondary">{unchangedCaption()}</p>
        ) : null}
      </header>

      <div
        className="flex gap-1.5 md:hidden"
        role="tablist"
        aria-label="Chọn phiên bản trên màn hình nhỏ"
      >
        <PaneTab active={mobilePane === "v1"} onClick={() => onMobilePane("v1")} label="V1" />
        <PaneTab active={mobilePane === "v2"} onClick={() => onMobilePane("v2")} label="V2" />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <VersionColumn
          side="v1"
          documentTitle={v1Title}
          text={clause.v1_text}
          emptyLabel={absenceMessage(status, "v1")}
          segments={highlightSegments(clause.v1_text ?? "", diffs, "v1", status)}
          emphasize={showDiff}
          hiddenOnMobile={mobilePane !== "v1"}
        />
        <VersionColumn
          side="v2"
          documentTitle={v2Title}
          text={clause.v2_text}
          emptyLabel={absenceMessage(status, "v2")}
          segments={highlightSegments(clause.v2_text ?? "", diffs, "v2", status)}
          emphasize={showDiff}
          hiddenOnMobile={mobilePane !== "v2"}
        />
      </div>

      {showDiff && diffs.length > 0 ? (
        <section aria-labelledby="exact-changes-heading">
          <h3 id="exact-changes-heading" className="text-body-sm font-semibold text-primary">
            Thay đổi chính xác
          </h3>
          <ul className="mt-2 flex flex-col gap-2">
            {diffs.map((row, index) => {
              const formatted = formatExactDifference(row);
              return (
                <li
                  key={`${formatted.label}-${index}`}
                  className="rounded-md border border-border-default bg-elevated/50 px-3 py-2.5"
                >
                  <p className="text-caption font-medium text-secondary">
                    {valueTypeLabel(String(row.value_type ?? formatted.label))}
                  </p>
                  <p className="mt-1 text-body text-primary">
                    {formatted.oldDisplay}
                    <span className="mx-1.5 text-tertiary">→</span>
                    {formatted.newDisplay}
                  </p>
                  {formatted.delta || formatted.percent ? (
                    <p className="mt-0.5 text-caption text-secondary">
                      {[formatted.delta, formatted.percent].filter(Boolean).join(" · ")}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {risk ? (
        <section
          aria-labelledby="clause-risk-heading"
          className="rounded-md border border-border-default px-3 py-3"
        >
          <h3 id="clause-risk-heading" className="text-body-sm font-semibold text-primary">
            Rủi ro
          </h3>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <RiskBadge level={risk} />
            {category ? <span className="text-body-sm text-secondary">{category}</span> : null}
            {clause.risk?.risk_score != null && String(clause.risk.risk_score) !== "" ? (
              <span className="text-caption text-tertiary">Điểm {String(clause.risk.risk_score)}</span>
            ) : null}
          </div>
          <p className="mt-2 text-body-sm text-secondary">{riskLevelHelp(risk)}</p>
          {clause.risk?.reason ? (
            <p className="mt-1 text-body-sm text-secondary">{String(clause.risk.reason)}</p>
          ) : null}
          {rules.length > 0 ? (
            <p className="mt-2 text-caption text-tertiary">Quy tắc: {rules.join(" · ")}</p>
          ) : null}
        </section>
      ) : null}

      {shouldShowAiAnalysis(status) && analysis ? (
        <section
          aria-labelledby="clause-ai-heading"
          className="rounded-md border border-border-default bg-elevated/40 px-3 py-3"
        >
          <h3 id="clause-ai-heading" className="text-caption font-semibold uppercase tracking-wide text-tertiary">
            Phân tích AI
          </h3>
          <p className="mt-1 text-body-sm font-medium text-secondary">Vì sao cần rà soát</p>
          <p className="mt-1 text-body-sm text-secondary">{analysis}</p>
          <p className="mt-2 text-caption text-tertiary">
            Đây là diễn giải, không phải nguyên văn hợp đồng hay sự kiện pháp lý đã xác minh độc lập.
          </p>
        </section>
      ) : null}

      <section aria-labelledby="clause-evidence-heading">
        <h3 id="clause-evidence-heading" className="text-body-sm font-semibold text-primary">
          Bằng chứng
        </h3>
        <p className="mt-1 text-caption text-tertiary">
          {evState === "verified"
            ? "Trích dẫn đã xác minh."
            : evState === "unavailable"
              ? "Không có bằng chứng"
              : evidenceStateLabel(evState)}
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <EvidenceColumn
            label="Phiên bản 1"
            items={status === "ADDED" ? [] : evidenceForSide(clause, "OLD")}
            emptyLabel={
              status === "ADDED"
                ? "Không xác định được điều khoản tương ứng ở V1"
                : "Không có bằng chứng"
            }
            workspaceId={workspaceId}
            fallbackDocumentId={v1Doc?.document_id}
            fallbackVersionId={v1Doc?.document_version_id}
          />
          <EvidenceColumn
            label="Phiên bản 2"
            items={status === "REMOVED" ? [] : evidenceForSide(clause, "NEW")}
            emptyLabel={
              status === "REMOVED"
                ? "Không xác định được điều khoản tương ứng ở V2"
                : "Không có bằng chứng"
            }
            workspaceId={workspaceId}
            fallbackDocumentId={v2Doc?.document_id}
            fallbackVersionId={v2Doc?.document_version_id}
          />
        </div>
      </section>
    </div>
  );
}

function PaneTab({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "flex-1 rounded-md border px-3 py-1.5 text-caption font-medium",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
        active
          ? "border-accent-primary/40 bg-accent-primary/10 text-primary"
          : "border-border-default text-secondary",
      )}
    >
      {label}
    </button>
  );
}

function VersionColumn({
  side,
  documentTitle,
  text,
  emptyLabel,
  segments,
  emphasize,
  hiddenOnMobile,
}: {
  side: "v1" | "v2";
  documentTitle: string;
  text?: string | null;
  emptyLabel: string;
  segments: HighlightSegment[];
  emphasize: boolean;
  hiddenOnMobile: boolean;
}) {
  const heading = columnHeading(side);
  return (
    <section
      aria-labelledby={`clause-col-${side}`}
      className={cn(
        "flex min-h-[16rem] min-w-0 flex-col rounded-md border border-border-default bg-doc-bg",
        hiddenOnMobile && "hidden md:flex",
      )}
    >
      <div className="border-b border-border-default px-3 py-2.5">
        <p
          id={`clause-col-${side}`}
          className="text-caption font-semibold uppercase tracking-wide text-tertiary"
        >
          {heading.kicker}
        </p>
        <p className="text-body-sm font-medium text-primary">{heading.title}</p>
        <p className="text-caption text-tertiary">{documentTitle}</p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {text ? (
          <p className="whitespace-pre-wrap font-serif text-body leading-relaxed text-doc-text">
            {emphasize
              ? segments.map((segment, index) => (
                  <span
                    key={`${side}-${index}`}
                    className={cn(
                      segment.kind === "removed" && "bg-danger-soft/80",
                      segment.kind === "added" && "bg-success/15",
                    )}
                  >
                    {segment.text}
                  </span>
                ))
              : text}
          </p>
        ) : (
          <p className="text-body-sm text-tertiary">{emptyLabel}</p>
        )}
      </div>
    </section>
  );
}

function EvidenceColumn({
  label,
  items,
  emptyLabel,
  workspaceId,
  fallbackDocumentId,
  fallbackVersionId,
}: {
  label: string;
  items: ContractEvidenceRef[];
  emptyLabel: string;
  workspaceId: string;
  fallbackDocumentId?: string | null;
  fallbackVersionId?: string | null;
}) {
  return (
    <div>
      <p className="text-caption font-medium text-secondary">{label}</p>
      {items.length === 0 ? (
        <p className="mt-1 text-caption text-tertiary">{emptyLabel}</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1">
          {items.map((item, index) => {
            const href = evidenceViewerHref(
              workspaceId,
              item,
              fallbackDocumentId,
              fallbackVersionId,
            );
            const clause = item.clause_id ? `Điều ${displayClauseId(item.clause_id)}` : null;
            const page = item.page_number ? `Trang ${item.page_number}` : null;
            const text = [clause, page].filter(Boolean).join(" · ") || "Mở nguồn";
            return (
              <li key={item.evidence_id ?? `${label}-${index}`}>
                {href ? (
                  <Link
                    href={href}
                    className="inline-flex items-center gap-1 text-caption text-accent-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
                  >
                    <FileText className="h-3 w-3" aria-hidden />
                    {text}
                  </Link>
                ) : (
                  <span className="text-caption text-tertiary">{text}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
