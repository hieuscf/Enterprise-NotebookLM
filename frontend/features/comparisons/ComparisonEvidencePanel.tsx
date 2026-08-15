/**
 * =============================================================================
 * File: ComparisonEvidencePanel.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TASK-CMP-19 evidence & citation inspector for comparison findings.
 * Responsibilities:
 *   - Present backend evidence, verification, excerpts, and source navigation
 *   - Keep AI analysis visually secondary to source evidence
 * Dependencies:
 *   - comparison-evidence helpers, comparison-badges, existing document viewer
 * Public Exports:
 *   - ComparisonEvidencePanel
 * Database/Table: N/A
 * Related Modules: ComparisonSummaryView, ClauseComparisonView, DocumentDetailView
 * Important Notes: Backend is source of truth. Do not infer verification.
 *   Preserve comparison context; z-[60] stacks above the CMP-18 overlay.
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ArrowLeft,
  Check,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { saveCitationFocus } from "@/features/chat/citation/citation-session";
import {
  EvidenceStateBadge,
  RiskBadge,
  StatusBadge,
} from "@/features/comparisons/comparison-badges";
import { shouldShowAiAnalysis } from "@/features/comparisons/clause-view";
import { ComparisonComments } from "@/features/comparisons/ComparisonComments";
import { ComparisonReviewActions } from "@/features/comparisons/ComparisonReviewActions";
import type { ReviewMap } from "@/features/comparisons/comparison-review";
import {
  absenceStatus,
  aiCitationRefs,
  buildEvidenceSourceHref,
  copyCitationText,
  documentTitleForSide,
  evidenceCountLabel,
  fallbackDocumentForSide,
  findingContext,
  flattenEvidenceItems,
  groupedEvidence,
  itemVerificationNote,
  sourceLocationLabel,
  sourceMetadataLines,
  versionGroupLabel,
  type EvidenceListItem,
  type EvidenceVersionGroup,
} from "@/features/comparisons/comparison-evidence";
import {
  clauseRiskLevel,
  displayClauseId,
  evidenceState,
  evidenceStateLabel,
  explanationText,
  formatExactDifference,
  riskLevelHelp,
} from "@/features/comparisons/comparison-summary";
import { cn } from "@/lib/utils";
import type {
  ComparisonComment,
  ComparisonCommentTarget,
  ComparisonReviewStatus,
  ContractClauseResult,
  ContractComparisonReport,
  DocumentMeta,
} from "@/types/comparisons";

type Props = {
  open: boolean;
  workspaceId: string;
  report: ContractComparisonReport | null;
  clause: ContractClauseResult | null;
  documentMeta?: Record<string, DocumentMeta>;
  focusEvidenceId?: string | null;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
  onRetry?: () => void;
  onFocusEvidence?: (evidenceId: string) => void;
  canEdit?: boolean;
  reviewing?: boolean;
  commenting?: boolean;
  review?: ReviewMap | null;
  comments?: ComparisonComment[] | null;
  onReviewChange?: (clauseId: string, status: ComparisonReviewStatus) => void;
  onCommentCreate?: (
    clauseId: string,
    body: string,
    targetType: ComparisonCommentTarget,
    targetId?: string | null,
  ) => void;
  onCommentUpdate?: (commentId: string, body: string) => void;
  onCommentDelete?: (commentId: string) => void;
};

export function ComparisonEvidencePanel({
  open,
  workspaceId,
  report,
  clause,
  documentMeta = {},
  focusEvidenceId = null,
  loading = false,
  error = null,
  onClose,
  onRetry,
  onFocusEvidence,
  canEdit = false,
  reviewing = false,
  commenting = false,
  review = null,
  comments = null,
  onReviewChange,
  onCommentCreate,
  onCommentUpdate,
  onCommentDelete,
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      onClose();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !focusEvidenceId) return;
    const node = document.querySelector(`[data-evidence-key="${cssEscape(focusEvidenceId)}"]`);
    node?.scrollIntoView({ block: "nearest" });
  }, [open, focusEvidenceId, clause?.clause_id]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex justify-end" role="presentation">
      <button
        type="button"
        aria-label="Đóng bảng bằng chứng"
        className="absolute inset-0 bg-primary/35"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative flex h-full w-full max-w-lg flex-col border-l border-border-default bg-surface shadow-lg sm:w-[28rem] md:w-[32rem]"
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border-default px-4 py-3">
          <div className="min-w-0">
            <p className="text-caption font-medium uppercase tracking-wider text-tertiary">
              Bằng chứng
            </p>
            <h2 id={titleId} className="mt-1 text-h3 text-primary">
              {clause ? `Điều ${displayClauseId(clause.clause_id)}` : "Bằng chứng"}
            </h2>
            {clause?.risk?.risk_category ? (
              <p className="mt-0.5 text-caption text-secondary">
                {String(clause.risk.risk_category)}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            ref={closeRef}
            onClick={onClose}
            className={iconButtonClass}
            aria-label="Đóng bảng bằng chứng"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {loading ? <LoadingState /> : null}
          {!loading && error ? (
            <ErrorState message={error} onRetry={onRetry} onBack={onClose} />
          ) : null}
          {!loading && !error && !clause ? (
            <ErrorState
              message="Không tải được bằng chứng."
              onRetry={onRetry}
              onBack={onClose}
            />
          ) : null}
          {!loading && !error && clause ? (
            <EvidenceBody
              clause={clause}
              workspaceId={workspaceId}
              report={report}
              documentMeta={documentMeta}
              focusEvidenceId={focusEvidenceId}
              onFocusEvidence={onFocusEvidence}
              onBack={onClose}
              canEdit={canEdit}
              reviewing={reviewing}
              commenting={commenting}
              review={review}
              comments={comments}
              onReviewChange={onReviewChange}
              onCommentCreate={onCommentCreate}
              onCommentUpdate={onCommentUpdate}
              onCommentDelete={onCommentDelete}
            />
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return value.replace(/["\\]/g, "\\$&");
}

const iconButtonClass = cn(
  "flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-secondary",
  "hover:bg-elevated hover:text-primary",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
);

const actionButtonClass = cn(
  "inline-flex h-9 items-center gap-1.5 rounded-md border border-border-default px-3",
  "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
  "disabled:cursor-not-allowed disabled:opacity-40",
);

function LoadingState() {
  return (
    <div role="status" className="flex items-center gap-2 py-16 text-body-sm text-secondary">
      <Loader2 className="h-4 w-4 animate-spin text-accent-primary" aria-hidden />
      Đang tải bằng chứng…
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
          <button type="button" onClick={onRetry} className={actionButtonClass}>
            Thử lại
          </button>
        ) : null}
        <button type="button" onClick={onBack} className={actionButtonClass}>
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Quay lại điều khoản
        </button>
      </div>
    </div>
  );
}

function EvidenceBody({
  clause,
  workspaceId,
  report,
  documentMeta,
  focusEvidenceId,
  onFocusEvidence,
  onBack,
  canEdit,
  reviewing,
  commenting,
  review,
  comments,
  onReviewChange,
  onCommentCreate,
  onCommentUpdate,
  onCommentDelete,
}: {
  clause: ContractClauseResult;
  workspaceId: string;
  report: ContractComparisonReport | null;
  documentMeta: Record<string, DocumentMeta>;
  focusEvidenceId: string | null;
  onFocusEvidence?: (evidenceId: string) => void;
  onBack: () => void;
  canEdit: boolean;
  reviewing: boolean;
  commenting?: boolean;
  review: ReviewMap | null;
  comments?: ComparisonComment[] | null;
  onReviewChange?: (clauseId: string, status: ComparisonReviewStatus) => void;
  onCommentCreate?: (
    clauseId: string,
    body: string,
    targetType: ComparisonCommentTarget,
    targetId?: string | null,
  ) => void;
  onCommentUpdate?: (commentId: string, body: string) => void;
  onCommentDelete?: (commentId: string) => void;
}) {
  const status = String(clause.status).toUpperCase();
  const risk = clauseRiskLevel(clause);
  const findingState = evidenceState(clause);
  const groups = groupedEvidence(clause);
  const items = flattenEvidenceItems(clause);
  const diffs = clause.exact_differences ?? [];
  const analysis = shouldShowAiAnalysis(status) ? explanationText(clause) : null;
  const citations = aiCitationRefs(clause);
  const message = clause.verification?.human_message?.trim() || null;
  const v1Absence = absenceStatus(clause, "v1");
  const v2Absence = absenceStatus(clause, "v2");

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap gap-1.5">
        <StatusBadge status={status} />
        <RiskBadge level={risk} />
        <EvidenceStateBadge state={findingState} />
      </div>

      <section aria-labelledby="evidence-finding-heading">
        <h3 id="evidence-finding-heading" className="text-caption font-semibold uppercase tracking-wide text-tertiary">
          Phát hiện
        </h3>
        <p className="mt-1 text-body-sm text-primary">{findingContext(clause)}</p>
      </section>

      <ComparisonReviewActions
        clauseId={clause.clause_id}
        review={review}
        canEdit={canEdit}
        saving={reviewing}
        onChange={(status) => onReviewChange?.(clause.clause_id, status)}
      />

      <ComparisonComments
        clauseId={clause.clause_id}
        comments={comments}
        canEdit={canEdit}
        saving={commenting}
        onCreate={(body, targetType, targetId) =>
          onCommentCreate?.(clause.clause_id, body, targetType, targetId)
        }
        onUpdate={(commentId, body) => onCommentUpdate?.(commentId, body)}
        onDelete={(commentId) => onCommentDelete?.(commentId)}
      />

      {diffs.length > 0 ? (
        <section aria-labelledby="evidence-change-heading">
          <h3 id="evidence-change-heading" className="text-caption font-semibold uppercase tracking-wide text-tertiary">
            Thay đổi
          </h3>
          <ul className="mt-2 flex flex-col gap-2">
            {diffs.map((row, index) => {
              const formatted = formatExactDifference(row);
              return (
                <li
                  key={`${formatted.label}-${index}`}
                  className="rounded-md border border-border-default bg-elevated/40 px-3 py-2"
                >
                  <p className="text-caption font-medium text-secondary">{formatted.label}</p>
                  <p className="mt-1 font-serif text-body-sm text-doc-text">
                    {formatted.oldDisplay}
                    <span className="mx-1.5 text-tertiary">→</span>
                    {formatted.newDisplay}
                  </p>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {risk ? (
        <section aria-labelledby="evidence-risk-heading">
          <h3 id="evidence-risk-heading" className="text-caption font-semibold uppercase tracking-wide text-tertiary">
            Rủi ro
          </h3>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <RiskBadge level={risk} />
            {clause.risk?.risk_category ? (
              <span className="text-body-sm text-secondary">{String(clause.risk.risk_category)}</span>
            ) : null}
          </div>
          <p className="mt-1 text-caption text-secondary">{riskLevelHelp(risk)}</p>
          {clause.risk?.reason ? (
            <p className="mt-2 text-body-sm text-secondary">{String(clause.risk.reason)}</p>
          ) : null}
        </section>
      ) : null}

      <section aria-labelledby="evidence-source-heading">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 id="evidence-source-heading" className="text-body-sm font-semibold text-primary">
            Bằng chứng nguồn
          </h3>
          <p className="text-caption text-tertiary">{evidenceCountLabel(items.length)}</p>
        </div>
        <p className="mt-1 text-caption text-tertiary">
          Nguyên văn tài liệu — không phải diễn giải AI.
        </p>

        {items.length === 0 && !v1Absence && !v2Absence ? (
          <p role="status" className="mt-3 text-body-sm text-secondary">
            Không có bằng chứng
          </p>
        ) : (
          <div className="mt-3 flex flex-col gap-4">
            <EvidenceGroup
              side="v1"
              items={groups.v1}
              absence={v1Absence}
              workspaceId={workspaceId}
              report={report}
              documentMeta={documentMeta}
              clause={clause}
              focusEvidenceId={focusEvidenceId}
              comments={comments}
              canEdit={canEdit}
              commenting={commenting}
              onCommentCreate={onCommentCreate}
              onCommentUpdate={onCommentUpdate}
              onCommentDelete={onCommentDelete}
            />
            <EvidenceGroup
              side="v2"
              items={groups.v2}
              absence={v2Absence}
              workspaceId={workspaceId}
              report={report}
              documentMeta={documentMeta}
              clause={clause}
              focusEvidenceId={focusEvidenceId}
              comments={comments}
              canEdit={canEdit}
              commenting={commenting}
              onCommentCreate={onCommentCreate}
              onCommentUpdate={onCommentUpdate}
              onCommentDelete={onCommentDelete}
            />
            {groups.other.length > 0 ? (
              <EvidenceGroup
                side="other"
                items={groups.other}
                absence={null}
                workspaceId={workspaceId}
                report={report}
                documentMeta={documentMeta}
                clause={clause}
                focusEvidenceId={focusEvidenceId}
                comments={comments}
                canEdit={canEdit}
                commenting={commenting}
                onCommentCreate={onCommentCreate}
                onCommentUpdate={onCommentUpdate}
                onCommentDelete={onCommentDelete}
              />
            ) : null}
          </div>
        )}
      </section>

      <section aria-labelledby="evidence-verification-heading">
        <h3
          id="evidence-verification-heading"
          className="text-caption font-semibold uppercase tracking-wide text-tertiary"
        >
          Xác minh
        </h3>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <EvidenceStateBadge state={findingState} />
        </div>
        {message ? (
          <p className="mt-2 text-body-sm text-secondary">{message}</p>
        ) : (
          <p className="mt-2 text-caption text-tertiary">
            {findingState === "verified"
              ? "Trích dẫn đã được xác minh với tài liệu nguồn."
              : findingState === "partial"
                ? "Một phần nguồn đã được xác minh."
                : findingState === "unavailable"
                  ? "Không có bằng chứng"
                  : "Trích dẫn này chưa được xác minh đầy đủ với nguồn."}
          </p>
        )}
      </section>

      {analysis ? (
        <section
          aria-labelledby="evidence-ai-heading"
          className="rounded-md border border-border-default bg-elevated/30 px-3 py-3"
        >
          <h3 id="evidence-ai-heading" className="text-caption font-semibold uppercase tracking-wide text-tertiary">
            Phân tích AI
          </h3>
          <p className="mt-1 text-body-sm text-secondary">{analysis}</p>
          {citations.length > 0 ? (
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Trích dẫn trong phân tích AI">
              {citations.map((citation) => (
                <li key={citation.evidenceId}>
                  <button
                    type="button"
                    onClick={() => onFocusEvidence?.(citation.evidenceId)}
                    className={cn(
                      "inline-flex items-center rounded-sm border px-1.5 py-0.5 font-mono text-caption",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                      focusEvidenceId === citation.evidenceId
                        ? "border-accent-primary/40 bg-accent-primary/10 text-primary"
                        : "border-border-default text-secondary hover:bg-elevated",
                    )}
                    aria-label={aiCitationAria(citation.index, citation.item)}
                  >
                    [{citation.index}]
                    {citation.item ? (
                      <span className="ml-1 font-sans">
                        {citation.item.side === "v1" ? "V1" : citation.item.side === "v2" ? "V2" : "Nguồn"}
                        {citation.item.evidence.page_number
                          ? ` · Trang ${citation.item.evidence.page_number}`
                          : ""}
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="mt-2 text-caption text-tertiary">
            Đây là diễn giải, không phải nguyên văn hợp đồng.
          </p>
        </section>
      ) : null}

      <SourceActions
        workspaceId={workspaceId}
        report={report}
        groups={groups}
        documentMeta={documentMeta}
      />

      <button type="button" onClick={onBack} className={actionButtonClass}>
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Quay lại điều khoản
      </button>
    </div>
  );
}

function aiCitationAria(index: number, item: EvidenceListItem | null): string {
  if (!item) return `Nguồn ${index}`;
  const page =
    typeof item.evidence.page_number === "number" && item.evidence.page_number > 0
      ? `trang ${item.evidence.page_number}`
      : null;
  return ["Nguồn", String(index), versionGroupLabel(item.side), page, evidenceStateLabel(item.verification)]
    .filter(Boolean)
    .join(", ");
}

function EvidenceGroup({
  side,
  items,
  absence,
  workspaceId,
  report,
  documentMeta,
  clause,
  focusEvidenceId,
  comments,
  canEdit,
  commenting,
  onCommentCreate,
  onCommentUpdate,
  onCommentDelete,
}: {
  side: EvidenceVersionGroup;
  items: EvidenceListItem[];
  absence: string | null;
  workspaceId: string;
  report: ContractComparisonReport | null;
  documentMeta: Record<string, DocumentMeta>;
  clause: ContractClauseResult;
  focusEvidenceId: string | null;
  comments?: ComparisonComment[] | null;
  canEdit?: boolean;
  commenting?: boolean;
  onCommentCreate?: (
    clauseId: string,
    body: string,
    targetType: ComparisonCommentTarget,
    targetId?: string | null,
  ) => void;
  onCommentUpdate?: (commentId: string, body: string) => void;
  onCommentDelete?: (commentId: string) => void;
}) {
  const title = documentTitleForSide(report, side, documentMeta);
  const fallback = fallbackDocumentForSide(report, side === "other" ? "v1" : side);
  return (
    <div>
      <h4 className="text-caption font-semibold uppercase tracking-wide text-secondary">
        {versionGroupLabel(side)}
      </h4>
      {absence && items.length === 0 ? (
        <p className="mt-1 text-body-sm text-tertiary">{absence}</p>
      ) : null}
      {items.length === 0 && !absence ? (
        <p className="mt-1 text-caption text-tertiary">Không có bằng chứng</p>
      ) : null}
      {items.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-2">
          {items.map((item, index) => (
            <li key={item.key}>
              <EvidenceCard
                index={index + 1}
                item={item}
                clause={clause}
                documentTitle={title}
                workspaceId={workspaceId}
                fallbackDocumentId={fallback.documentId}
                fallbackVersionId={fallback.versionId}
                focused={Boolean(
                  focusEvidenceId &&
                    (item.evidence.evidence_id === focusEvidenceId || item.key === focusEvidenceId),
                )}
                comments={comments}
                canEdit={canEdit}
                commenting={commenting}
                onCommentCreate={onCommentCreate}
                onCommentUpdate={onCommentUpdate}
                onCommentDelete={onCommentDelete}
              />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function EvidenceCard({
  index,
  item,
  clause,
  documentTitle,
  workspaceId,
  fallbackDocumentId,
  fallbackVersionId,
  focused,
  comments,
  canEdit,
  commenting,
  onCommentCreate,
  onCommentUpdate,
  onCommentDelete,
}: {
  index: number;
  item: EvidenceListItem;
  clause: ContractClauseResult;
  documentTitle: string | null;
  workspaceId: string;
  fallbackDocumentId: string | null;
  fallbackVersionId: string | null;
  focused: boolean;
  comments?: ComparisonComment[] | null;
  canEdit?: boolean;
  commenting?: boolean;
  onCommentCreate?: (
    clauseId: string,
    body: string,
    targetType: ComparisonCommentTarget,
    targetId?: string | null,
  ) => void;
  onCommentUpdate?: (commentId: string, body: string) => void;
  onCommentDelete?: (commentId: string) => void;
}) {
  const note = itemVerificationNote(clause, item.evidence);
  const meta = sourceMetadataLines(item.evidence, versionGroupLabel(item.side), documentTitle);
  const location = sourceLocationLabel(item.evidence, documentTitle);
  const href = buildEvidenceSourceHref(
    workspaceId,
    item.evidence,
    fallbackDocumentId,
    fallbackVersionId,
  );
  const documentId = item.evidence.document_id || fallbackDocumentId;
  const versionId = item.evidence.document_version_id || fallbackVersionId;

  function persistFocus() {
    if (!documentId) return;
    saveCitationFocus(workspaceId, {
      citationId: item.evidence.evidence_id || item.key,
      documentId,
      textSnippet: item.excerpt ?? "",
      page: item.evidence.page_number ?? null,
      chunkId: item.evidence.chunk_id ?? null,
      versionId: versionId ?? null,
      verified: item.verification === "verified",
      documentTitle: documentTitle ?? undefined,
    });
  }

  return (
    <article
      data-evidence-key={item.evidence.evidence_id || item.key}
      aria-current={focused ? "true" : undefined}
      className={cn(
        "rounded-md border bg-doc-bg px-3 py-3",
        focused ? "border-accent-primary/40" : "border-border-default",
        item.primary && "border-l-[3px] border-l-accent-primary",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-caption font-medium text-secondary">
          {index}. {location}
        </p>
        {item.primary ? (
          <span className="text-caption font-medium text-accent-primary">Bằng chứng chính</span>
        ) : null}
      </div>
      <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-caption">
        {meta.map((row) => (
          <div key={row.label} className="contents">
            <dt className="text-tertiary">{row.label}</dt>
            <dd className="text-secondary">{row.value}</dd>
          </div>
        ))}
      </dl>
      {item.excerpt ? (
        <blockquote className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap border-l-2 border-border-strong pl-3 font-serif text-body-sm leading-relaxed text-doc-text">
          {item.excerpt}
        </blockquote>
      ) : (
        <p className="mt-2 text-caption text-tertiary">Không có đoạn trích nguồn.</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <EvidenceStateBadge state={item.verification} />
        {note ? <p className="text-caption text-secondary">{note}</p> : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {href ? (
          <Link
            href={href}
            onClick={persistFocus}
            className={actionButtonClass}
            aria-label={`Mở nguồn ${versionGroupLabel(item.side)} trong tài liệu`}
          >
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            Mở nguồn
          </Link>
        ) : (
          <span className="text-caption text-tertiary">Không mở được nguồn</span>
        )}
        <CopyExcerptButton item={item} versionLabel={versionGroupLabel(item.side)} />
      </div>
      {item.evidence.evidence_id ? (
        <div className="mt-3">
          <ComparisonComments
            clauseId={clause.clause_id}
            comments={comments}
            canEdit={Boolean(canEdit)}
            saving={commenting}
            compact
            targetType="EVIDENCE"
            targetId={item.evidence.evidence_id}
            onCreate={(body, targetType, targetId) =>
              onCommentCreate?.(clause.clause_id, body, targetType, targetId)
            }
            onUpdate={(commentId, body) => onCommentUpdate?.(commentId, body)}
            onDelete={(commentId) => onCommentDelete?.(commentId)}
          />
        </div>
      ) : null}
    </article>
  );
}

function CopyExcerptButton({
  item,
  versionLabel,
}: {
  item: EvidenceListItem;
  versionLabel: string;
}) {
  const [copied, setCopied] = useState(false);
  const text = copyCitationText(item, versionLabel);
  if (!text) return null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <button
      type="button"
      onClick={() => void copy()}
      className={actionButtonClass}
      aria-label="Sao chép đoạn trích nguồn"
    >
      {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      {copied ? "Đã sao chép" : "Sao chép đoạn trích"}
    </button>
  );
}

function SourceActions({
  workspaceId,
  report,
  groups,
  documentMeta,
}: {
  workspaceId: string;
  report: ContractComparisonReport | null;
  groups: ReturnType<typeof groupedEvidence>;
  documentMeta: Record<string, DocumentMeta>;
}) {
  const v1 = groups.v1[0];
  const v2 = groups.v2[0];
  const v1Fallback = fallbackDocumentForSide(report, "v1");
  const v2Fallback = fallbackDocumentForSide(report, "v2");
  const v1Href = v1
    ? buildEvidenceSourceHref(
        workspaceId,
        v1.evidence,
        v1Fallback.documentId,
        v1Fallback.versionId,
      )
    : null;
  const v2Href = v2
    ? buildEvidenceSourceHref(
        workspaceId,
        v2.evidence,
        v2Fallback.documentId,
        v2Fallback.versionId,
      )
    : null;
  if (!v1Href && !v2Href) return null;

  function persist(item: EvidenceListItem, side: EvidenceVersionGroup) {
    const fallback = fallbackDocumentForSide(report, side);
    const documentId = item.evidence.document_id || fallback.documentId;
    if (!documentId) return;
    saveCitationFocus(workspaceId, {
      citationId: item.evidence.evidence_id || item.key,
      documentId,
      textSnippet: item.excerpt ?? "",
      page: item.evidence.page_number ?? null,
      chunkId: item.evidence.chunk_id ?? null,
      versionId: item.evidence.document_version_id || fallback.versionId,
      verified: item.verification === "verified",
      documentTitle: documentTitleForSide(report, side, documentMeta) ?? undefined,
    });
  }

  return (
    <div className="flex flex-wrap gap-2 border-t border-border-default pt-4">
      {v1 && v1Href ? (
        <Link
          href={v1Href}
          onClick={() => persist(v1, "v1")}
          className={actionButtonClass}
        >
          <FileText className="h-3.5 w-3.5" aria-hidden />
          Mở nguồn V1
        </Link>
      ) : null}
      {v2 && v2Href ? (
        <Link
          href={v2Href}
          onClick={() => persist(v2, "v2")}
          className={actionButtonClass}
        >
          <FileText className="h-3.5 w-3.5" aria-hidden />
          Mở nguồn V2
        </Link>
      ) : null}
    </div>
  );
}
