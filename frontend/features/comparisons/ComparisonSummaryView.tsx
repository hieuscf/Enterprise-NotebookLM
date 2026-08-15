/**
 * =============================================================================
 * File: ComparisonSummaryView.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TASK-CMP-17 clause-level Comparison Summary for CMP-15/16 reports,
 *   with TASK-CMP-21 combined filtering and search.
 * Responsibilities:
 *   - Header V1 vs V2, status, summary stats, risk, distribution, priority
 *   - Combined filter/search; open CMP-18 side-by-side workspace
 * Dependencies:
 *   - comparison-summary, comparison-filter, ClauseComparisonView, design tokens
 * Public Exports:
 *   - ComparisonSummaryView
 * Database/Table: N/A
 * Related Modules: ComparisonResult, ClauseComparisonView, document viewer
 * Important Notes: Backend report is source of truth. No frontend risk/diff logic.
 * =============================================================================
 */

"use client";

import {
  ArrowRight,
  FileText,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { ClauseComparisonView } from "@/features/comparisons/ClauseComparisonView";
import { ComparisonEvidencePanel } from "@/features/comparisons/ComparisonEvidencePanel";
import { ComparisonFilterBar } from "@/features/comparisons/ComparisonFilterBar";
import {
  EvidenceStateBadge,
  ReviewBadge,
  RiskBadge,
  StatusBadge,
  riskToneClass,
} from "@/features/comparisons/comparison-badges";
import { clauseNav, resolveClauseId } from "@/features/comparisons/clause-view";
import { aiCitationRefs } from "@/features/comparisons/comparison-evidence";
import {
  applyComparisonQuery,
  clauseCategories,
  EMPTY_COMPARISON_QUERY,
  facetCounts,
  isQueryActive,
  queryScopeLabel,
  type ComparisonQuery,
} from "@/features/comparisons/comparison-filter";
import { ComparisonAuditTrail } from "@/features/comparisons/ComparisonAuditTrail";
import { ComparisonComments } from "@/features/comparisons/ComparisonComments";
import { ComparisonReviewActions } from "@/features/comparisons/ComparisonReviewActions";
import {
  commentCount,
  commentCountLabel,
  exactDifferenceTargetId,
} from "@/features/comparisons/comparison-comments";
import {
  reviewProgress,
  reviewState,
  type ReviewMap,
} from "@/features/comparisons/comparison-review";
import {
  authoritativeSummary,
  clauseRiskLevel,
  clauseStatusCaption,
  comparisonUiStatus,
  displayClauseId,
  distributionPercents,
  documentLabel,
  documentViewerHref,
  evidenceForSide,
  evidenceLine,
  evidenceState,
  excerpt,
  explanationText,
  flattenClauses,
  formatExactDifference,
  hasMaterialChanges,
  priorityClauses,
  qualityWarningText,
  riskCountsFromReport,
  riskLevelHelp,
  riskLevelLabel,
  shortChangeSummary,
  statusBannerLabel,
} from "@/features/comparisons/comparison-summary";
import { formatComparisonDateTime } from "@/features/comparisons/comparison-format";
import { cn } from "@/lib/utils";
import type {
  Comparison,
  ComparisonAuditEvent,
  ComparisonComment,
  ComparisonCommentTarget,
  ComparisonReviewStatus,
  ContractClauseResult,
  ContractComparisonReport,
  ContractEvidenceRef,
  DocumentMeta,
} from "@/types/comparisons";

type Props = {
  workspaceId: string;
  comparison: Comparison;
  report: ContractComparisonReport;
  documentMeta?: Record<string, DocumentMeta>;
  initialClauseId?: string | null;
  canEdit?: boolean;
  reviewing?: boolean;
  commenting?: boolean;
  onReviewChange?: (clauseId: string, status: ComparisonReviewStatus) => void;
  onCommentCreate?: (
    clauseId: string,
    body: string,
    targetType: ComparisonCommentTarget,
    targetId?: string | null,
  ) => void;
  onCommentUpdate?: (commentId: string, body: string) => void;
  onCommentDelete?: (commentId: string) => void;
  onClauseChange?: (clauseId: string | null) => void;
  onClauseOpened?: (clauseId: string) => void;
  auditEvents?: ComparisonAuditEvent[];
  auditLoading?: boolean;
};

export function ComparisonSummaryView({
  workspaceId,
  comparison,
  report,
  documentMeta = {},
  initialClauseId = null,
  canEdit = false,
  reviewing = false,
  commenting = false,
  onReviewChange,
  onCommentCreate,
  onCommentUpdate,
  onCommentDelete,
  onClauseChange,
  onClauseOpened,
  auditEvents = [],
  auditLoading = false,
}: Props) {
  const summary = authoritativeSummary(report);
  const clauses = useMemo(() => flattenClauses(report), [report]);
  const priority = useMemo(() => priorityClauses(clauses).slice(0, 5), [clauses]);
  const risks = riskCountsFromReport(report);
  const dist = distributionPercents(summary);
  const uiStatus = comparisonUiStatus(comparison, report);
  const warning = qualityWarningText(report);

  const v1Id = comparison.document_ids[0];
  const v2Id = comparison.document_ids[1];
  const v1 = documentLabel(report.metadata?.document_v1, v1Id, documentMeta[v1Id ?? ""]);
  const v2 = documentLabel(report.metadata?.document_v2, v2Id, documentMeta[v2Id ?? ""]);
  const v1Href = documentViewerHref(
    workspaceId,
    report.metadata?.document_v1?.document_id ?? v1Id,
    report.metadata?.document_v1?.document_version_id ?? v1.versionId,
  );
  const v2Href = documentViewerHref(
    workspaceId,
    report.metadata?.document_v2?.document_id ?? v2Id,
    report.metadata?.document_v2?.document_version_id ?? v2.versionId,
  );

  const [query, setQuery] = useState<ComparisonQuery>(EMPTY_COMPARISON_QUERY);
  const resolvedInitial = resolveClauseId(clauses, initialClauseId);
  const defaultSelected =
    resolvedInitial ??
    (initialClauseId
      ? null
      : priority[0]?.clause_id ??
        clauses.find((c) => String(c.status).toUpperCase() !== "UNCHANGED")?.clause_id ??
        clauses[0]?.clause_id ??
        null);
  const [selectedId, setSelectedId] = useState<string | null>(defaultSelected);
  const [workspaceOpen, setWorkspaceOpen] = useState(Boolean(initialClauseId));
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [focusEvidenceId, setFocusEvidenceId] = useState<string | null>(null);
  const recordedInitialRef = useRef<string | null>(null);

  useEffect(() => {
    const resolved = resolveClauseId(clauses, initialClauseId);
    if (!resolved) return;
    setSelectedId(resolved);
    setWorkspaceOpen(true);
    if (recordedInitialRef.current === resolved) return;
    recordedInitialRef.current = resolved;
    onClauseOpened?.(resolved);
  }, [clauses, initialClauseId, onClauseOpened]);

  const visible = useMemo(
    () => applyComparisonQuery(clauses, comparison.review, query, comparison.comments),
    [clauses, comparison.comments, comparison.review, query],
  );
  const categories = useMemo(() => clauseCategories(clauses), [clauses]);
  const facets = useMemo(
    () => facetCounts(clauses, comparison.review, query, comparison.comments),
    [clauses, comparison.comments, comparison.review, query],
  );
  const selected = clauses.find((c) => c.clause_id === selectedId) ?? null;
  const nav = clauseNav(visible, selectedId);
  const showRiskFilters = risks.critical + risks.high + risks.medium + risks.low > 0;
  const noMaterial = summary ? !hasMaterialChanges(summary) : false;
  const progress = reviewProgress(
    clauses.map((clause) => clause.clause_id),
    comparison.review,
  );

  function openClause(clauseId: string) {
    setSelectedId(clauseId);
    setWorkspaceOpen(true);
    onClauseChange?.(clauseId);
    onClauseOpened?.(clauseId);
  }

  function closeWorkspace() {
    setWorkspaceOpen(false);
    setEvidenceOpen(false);
    setFocusEvidenceId(null);
    onClauseChange?.(null);
  }

  function openEvidence(clauseId: string, evidenceId?: string | null) {
    setSelectedId(clauseId);
    setFocusEvidenceId(evidenceId ?? null);
    setEvidenceOpen(true);
  }

  function closeEvidence() {
    setEvidenceOpen(false);
    setFocusEvidenceId(null);
  }

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 border-b border-border-default pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-caption font-medium text-accent-primary">
              So sánh hợp đồng
            </p>
            <h2 id="comparison-result-heading" className="mt-1 text-h3 text-primary">
              {v1.title}
              <span className="mx-2 text-tertiary" aria-hidden>
                →
              </span>
              {v2.title}
            </h2>
            <p className="mt-1 text-caption text-tertiary">
              {formatComparisonDateTime(comparison.created_at)}
            </p>
          </div>
          <StatusPill uiStatus={uiStatus} />
        </div>

        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-stretch">
          <VersionCard
            side="V1"
            title={v1.title}
            date={v1.date}
            href={v1Href}
          />
          <div className="hidden items-center justify-center sm:flex" aria-hidden>
            <ArrowRight className="h-4 w-4 text-tertiary" />
          </div>
          <VersionCard
            side="V2"
            title={v2.title}
            date={v2.date}
            href={v2Href}
          />
        </div>
      </header>

      <div
        role={uiStatus === "failed" ? "alert" : "status"}
        className={cn(
          "rounded-md border px-3 py-2.5 text-body-sm",
          uiStatus === "completed" && "border-success/30 bg-success/5 text-secondary",
          uiStatus === "warning" && "border-warning/35 bg-warning/5 text-secondary",
          uiStatus === "failed" && "border-danger/30 bg-danger-soft text-danger",
        )}
      >
        <p className="font-medium text-primary">{statusBannerLabel(uiStatus)}</p>
        {warning ? <p className="mt-1">{warning}</p> : null}
      </div>

      {summary ? (
        <section aria-labelledby="comparison-summary-heading" className="flex flex-col gap-3">
          <h3 id="comparison-summary-heading" className="text-body-sm font-semibold text-primary">
            Tổng quan
          </h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            <StatCard
              label="Điều khoản"
              value={summary.total_clauses}
              emphasize="quiet"
              onClick={() => setQuery({ ...query, status: "all" })}
            />
            <StatCard
              label="Không đổi"
              value={summary.unchanged}
              emphasize="quiet"
              pressed={query.status === "unchanged"}
              onClick={() => setQuery({ ...query, status: "unchanged" })}
            />
            <StatCard
              label="Đã sửa"
              value={summary.modified}
              emphasize="modified"
              pressed={query.status === "modified"}
              onClick={() => setQuery({ ...query, status: "modified" })}
            />
            <StatCard
              label="Thêm mới"
              value={summary.added}
              emphasize="added"
              pressed={query.status === "added"}
              onClick={() => setQuery({ ...query, status: "added" })}
            />
            <StatCard
              label="Đã xoá"
              value={summary.removed}
              emphasize="removed"
              pressed={query.status === "removed"}
              onClick={() => setQuery({ ...query, status: "removed" })}
            />
          </div>
          <ChangeDistribution summary={summary} dist={dist} />
        </section>
      ) : null}

      {noMaterial && summary ? (
        <div
          role="status"
          className="rounded-md border border-border-default bg-elevated px-3 py-3 text-body-sm text-secondary"
        >
          <p className="font-medium text-primary">Không phát hiện thay đổi vật chất</p>
          <p className="mt-1">
            {summary.total_clauses} điều khoản đã so sánh · {summary.unchanged} không đổi ·{" "}
            {summary.modified} đã sửa · {summary.added} thêm mới · {summary.removed} đã xoá.
          </p>
        </div>
      ) : null}

      <section aria-labelledby="risk-overview-heading" className="flex flex-col gap-3">
        <h3 id="risk-overview-heading" className="text-body-sm font-semibold text-primary">
          Rủi ro
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <RiskCountCard
            level="CRITICAL"
            count={risks.critical}
            pressed={query.risk === "CRITICAL"}
            onClick={() =>
              setQuery({ ...query, risk: query.risk === "CRITICAL" ? null : "CRITICAL" })
            }
          />
          <RiskCountCard
            level="HIGH"
            count={risks.high}
            pressed={query.risk === "HIGH"}
            onClick={() => setQuery({ ...query, risk: query.risk === "HIGH" ? null : "HIGH" })}
          />
          <RiskCountCard
            level="MEDIUM"
            count={risks.medium}
            pressed={query.risk === "MEDIUM"}
            onClick={() =>
              setQuery({ ...query, risk: query.risk === "MEDIUM" ? null : "MEDIUM" })
            }
          />
          <RiskCountCard
            level="LOW"
            count={risks.low}
            pressed={query.risk === "LOW"}
            onClick={() => setQuery({ ...query, risk: query.risk === "LOW" ? null : "LOW" })}
          />
        </div>
      </section>

      <section aria-labelledby="review-progress-heading" className="flex flex-col gap-2">
        <h3 id="review-progress-heading" className="text-body-sm font-semibold text-primary">
          Tiến độ rà soát
        </h3>
        <p className="text-body-sm text-secondary">
          {progress.reviewed} đã rà soát · {progress.needsAttention} cần chú ý · {progress.acknowledged}{" "}
          đã ghi nhận · {progress.open} chưa rà soát
          <span className="text-tertiary"> · {progress.total} điều khoản</span>
        </p>
      </section>

      {priority.length > 0 ? (
        <section aria-labelledby="priority-changes-heading" className="flex flex-col gap-3">
          <h3 id="priority-changes-heading" className="text-body-sm font-semibold text-primary">
            Thay đổi ưu tiên
          </h3>
          <ul className="flex flex-col gap-2">
            {priority.map((clause) => (
              <li key={clause.clause_id}>
                <PriorityChangeCard
                  clause={clause}
                  selected={selectedId === clause.clause_id}
                  reviewStatus={reviewState(comparison.review, clause.clause_id)}
                  onOpen={() => openClause(clause.clause_id)}
                  onOpenEvidence={() => openEvidence(clause.clause_id)}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="clause-list-heading" className="flex flex-col gap-3">
        <h3 id="clause-list-heading" className="text-body-sm font-semibold text-primary">
          So sánh điều khoản
        </h3>
        <ComparisonFilterBar
          query={query}
          total={clauses.length}
          visible={visible.length}
          facets={facets}
          categories={categories}
          showRiskFilters={showRiskFilters}
          onChange={setQuery}
        />

        <div className="grid gap-3 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <ul
            className="flex max-h-[32rem] flex-col gap-1 overflow-y-auto pr-0.5"
            aria-label="Danh sách điều khoản"
          >
            {visible.length === 0 ? (
              <li className="rounded-md border border-dashed border-border-default px-3 py-4 text-body-sm text-tertiary">
                <p>Không có điều khoản khớp bộ lọc.</p>
                {isQueryActive(query) ? (
                  <button
                    type="button"
                    onClick={() => setQuery({ ...EMPTY_COMPARISON_QUERY })}
                    className="mt-2 text-caption font-medium text-accent-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
                  >
                    Xóa bộ lọc
                  </button>
                ) : null}
              </li>
            ) : (
              visible.map((clause) => (
                <li key={clause.clause_id}>
                  <ClauseRow
                    clause={clause}
                    selected={selectedId === clause.clause_id}
                    reviewStatus={reviewState(comparison.review, clause.clause_id)}
                    commentCount={commentCount(comparison.comments, clause.clause_id)}
                    onSelect={() => openClause(clause.clause_id)}
                    onOpenEvidence={() => openEvidence(clause.clause_id)}
                  />
                </li>
              ))
            )}
          </ul>
          <ClauseDetailPanel
            clause={selected}
            onOpen={() => selected && openClause(selected.clause_id)}
            onOpenEvidence={(evidenceId) =>
              selected && openEvidence(selected.clause_id, evidenceId)
            }
            review={comparison.review}
            comments={comparison.comments}
            canEdit={canEdit}
            reviewing={reviewing}
            commenting={commenting}
            onReviewChange={onReviewChange}
            onCommentCreate={onCommentCreate}
            onCommentUpdate={onCommentUpdate}
            onCommentDelete={onCommentDelete}
          />
        </div>
      </section>

      <ComparisonAuditTrail
        events={auditEvents}
        selectedClauseId={selectedId}
        loading={auditLoading}
      />

      <ClauseComparisonView
        open={workspaceOpen}
        workspaceId={workspaceId}
        report={report}
        clause={selected}
        nav={nav}
        scopeLabel={queryScopeLabel(query)}
        evidenceOpen={evidenceOpen}
        error={
          workspaceOpen && initialClauseId && !resolveClauseId(clauses, initialClauseId) && !selected
            ? "Không tải được đối chiếu điều khoản này."
            : null
        }
        documentMeta={documentMeta}
        onClose={closeWorkspace}
        onPrev={() => nav.prevId && openClause(nav.prevId)}
        onNext={() => nav.nextId && openClause(nav.nextId)}
        onOpenEvidence={(evidenceId) => selected && openEvidence(selected.clause_id, evidenceId)}
        canEdit={canEdit}
        reviewing={reviewing}
        commenting={commenting}
        review={comparison.review}
        comments={comparison.comments}
        onReviewChange={onReviewChange}
        onCommentCreate={onCommentCreate}
        onCommentUpdate={onCommentUpdate}
        onCommentDelete={onCommentDelete}
        onRetry={
          initialClauseId
            ? () => {
                const resolved = resolveClauseId(clauses, initialClauseId);
                if (resolved) openClause(resolved);
              }
            : undefined
        }
      />
      <ComparisonEvidencePanel
        open={evidenceOpen}
        workspaceId={workspaceId}
        report={report}
        clause={selected}
        documentMeta={documentMeta}
        focusEvidenceId={focusEvidenceId}
        onClose={closeEvidence}
        onFocusEvidence={(evidenceId) => setFocusEvidenceId(evidenceId)}
        canEdit={canEdit}
        reviewing={reviewing}
        commenting={commenting}
        review={comparison.review}
        comments={comparison.comments}
        onReviewChange={onReviewChange}
        onCommentCreate={onCommentCreate}
        onCommentUpdate={onCommentUpdate}
        onCommentDelete={onCommentDelete}
        onRetry={
          selected
            ? () => openEvidence(selected.clause_id, focusEvidenceId)
            : undefined
        }
      />
    </div>
  );
}

function StatusPill({ uiStatus }: { uiStatus: ReturnType<typeof comparisonUiStatus> }) {
  return (
    <span
      className={cn(
        "rounded-full px-2.5 py-1 text-caption font-semibold",
        uiStatus === "completed" && "bg-success/10 text-success",
        uiStatus === "warning" && "bg-warning/10 text-warning",
        uiStatus === "failed" && "bg-danger-soft text-danger",
        uiStatus === "processing" && "bg-warning/10 text-warning",
      )}
    >
      {statusBannerLabel(uiStatus)}
    </span>
  );
}

function VersionCard({
  side,
  title,
  date,
  href,
}: {
  side: string;
  title: string;
  date: string | null;
  href: string | null;
}) {
  const inner = (
    <>
      <p className="text-caption font-semibold uppercase tracking-wide text-tertiary">
        {side}
      </p>
      <p className="mt-1 text-body-sm font-medium text-primary">{title}</p>
      {date ? (
        <p className="mt-0.5 text-caption text-tertiary">
          {formatComparisonDateTime(date)}
        </p>
      ) : null}
    </>
  );
  const className =
    "rounded-md border border-border-default bg-elevated/60 px-3 py-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40";
  if (href) {
    return (
      <Link href={href} className={cn(className, "hover:border-accent-primary/35")}>
        {inner}
      </Link>
    );
  }
  return <div className={className}>{inner}</div>;
}

function StatCard({
  label,
  value,
  emphasize,
  pressed = false,
  onClick,
}: {
  label: string;
  value: number;
  emphasize: "quiet" | "modified" | "added" | "removed";
  pressed?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      className={cn(
        "rounded-md border px-3 py-2.5 text-left",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
        emphasize === "quiet" && "border-border-default bg-elevated/40",
        emphasize === "modified" && "border-warning/30 bg-warning/5",
        emphasize === "added" && "border-info/30 bg-info/5",
        emphasize === "removed" && "border-danger/30 bg-danger-soft",
        pressed && "ring-2 ring-accent-primary/30",
      )}
    >
      <p className="text-caption text-tertiary">{label}</p>
      <p
        className={cn(
          "mt-1 text-h3 tabular-nums",
          emphasize === "quiet" && "text-secondary",
          emphasize === "modified" && "text-warning",
          emphasize === "added" && "text-info",
          emphasize === "removed" && "text-danger",
        )}
      >
        {value}
      </p>
    </button>
  );
}

function ChangeDistribution({
  summary,
  dist,
}: {
  summary: NonNullable<ReturnType<typeof authoritativeSummary>>;
  dist: ReturnType<typeof distributionPercents>;
}) {
  return (
    <div>
      <p className="mb-1.5 text-caption text-tertiary">Phân bố thay đổi</p>
      <div
        className="flex h-2.5 overflow-hidden rounded-sm bg-inset"
        role="img"
        aria-label={`Không đổi ${summary.unchanged}, đã sửa ${summary.modified}, thêm mới ${summary.added}, đã xoá ${summary.removed}`}
      >
        <span className="bg-border-strong" style={{ width: `${dist.unchanged}%` }} />
        <span className="bg-warning" style={{ width: `${dist.modified}%` }} />
        <span className="bg-info" style={{ width: `${dist.added}%` }} />
        <span className="bg-danger" style={{ width: `${dist.removed}%` }} />
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-caption text-secondary">
        <li>Không đổi {summary.unchanged}</li>
        <li>Đã sửa {summary.modified}</li>
        <li>Thêm mới {summary.added}</li>
        <li>Đã xoá {summary.removed}</li>
      </ul>
    </div>
  );
}

function RiskCountCard({
  level,
  count,
  pressed = false,
  onClick,
}: {
  level: string;
  count: number;
  pressed?: boolean;
  onClick?: () => void;
}) {
  const label = riskLevelLabel(level);
  const help = riskLevelHelp(level);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      className={cn(
        "rounded-md border px-3 py-2.5 text-left",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
        riskToneClass(level),
        pressed && "ring-2 ring-accent-primary/30",
      )}
    >
      <p className="text-caption font-semibold uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-h3 tabular-nums text-primary">{count}</p>
      <p className="mt-1 text-caption text-secondary">{help}</p>
    </button>
  );
}

function PriorityChangeCard({
  clause,
  selected,
  reviewStatus,
  onOpen,
  onOpenEvidence,
}: {
  clause: ContractClauseResult;
  selected: boolean;
  reviewStatus: ComparisonReviewStatus;
  onOpen: () => void;
  onOpenEvidence: () => void;
}) {
  const risk = clauseRiskLevel(clause);
  const analysis = explanationText(clause);
  return (
    <article
      className={cn(
        "rounded-md border px-3 py-3",
        selected ? "border-accent-primary/40 bg-accent-primary/5" : "border-border-default bg-surface",
        risk === "CRITICAL" && !selected && "border-danger/25",
        risk === "HIGH" && !selected && "border-warning/25",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-body-sm font-semibold text-primary">
          Điều {displayClauseId(clause.clause_id)}
        </span>
        <StatusBadge status={String(clause.status)} />
        <RiskBadge level={risk} />
        <ReviewBadge status={reviewStatus} />
      </div>
      <p className="mt-2 text-body-sm text-secondary">{shortChangeSummary(clause)}</p>
      {analysis ? (
        <p className="mt-2 border-l-2 border-border-strong pl-2 text-caption text-tertiary">
          <span className="font-medium text-secondary">Phân tích AI. </span>
          {excerpt(analysis, 180)}
        </p>
      ) : null}
      <p className="mt-2 text-caption text-tertiary">
        Bằng chứng: {evidenceLine(clause)}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex h-8 items-center rounded-md border border-border-default px-2.5 text-caption font-medium text-secondary hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
        >
          Mở đối chiếu
        </button>
        <button
          type="button"
          onClick={onOpenEvidence}
          className="inline-flex h-8 items-center rounded-md border border-border-default px-2.5 text-caption font-medium text-secondary hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
        >
          Bằng chứng
        </button>
      </div>
    </article>
  );
}

function ClauseRow({
  clause,
  selected,
  reviewStatus,
  commentCount: notes,
  onSelect,
  onOpenEvidence,
}: {
  clause: ContractClauseResult;
  selected: boolean;
  reviewStatus: ComparisonReviewStatus;
  commentCount: number;
  onSelect: () => void;
  onOpenEvidence: () => void;
}) {
  const status = String(clause.status).toUpperCase();
  const quiet = status === "UNCHANGED";
  return (
    <div
      className={cn(
        "flex items-stretch gap-1 rounded-md border",
        selected
          ? "border-accent-primary/40 bg-accent-primary/5"
          : quiet
            ? "border-transparent bg-transparent"
            : "border-border-default bg-surface",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-expanded={selected}
        aria-controls="clause-detail-panel"
        className={cn(
          "min-w-0 flex-1 px-3 py-2 text-left",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
          !selected && quiet && "hover:bg-elevated",
          !selected && !quiet && "hover:bg-elevated",
        )}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={cn("text-body-sm font-medium", quiet ? "text-secondary" : "text-primary")}>
            {displayClauseId(clause.clause_id)}
          </span>
          <StatusBadge status={status} />
          <RiskBadge level={clauseRiskLevel(clause)} />
          <ReviewBadge status={reviewStatus} />
          {notes > 0 ? (
            <span className="text-caption text-tertiary">{commentCountLabel(notes)}</span>
          ) : null}
        </div>
        <p className={cn("mt-1 text-caption", quiet ? "text-tertiary" : "text-secondary")}>
          {shortChangeSummary(clause)}
        </p>
        <p className="mt-0.5 text-caption text-tertiary">{evidenceLine(clause)}</p>
      </button>
      <button
        type="button"
        onClick={onOpenEvidence}
        className="shrink-0 self-center px-2 py-2 text-caption font-medium text-secondary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
        aria-label={`Xem bằng chứng điều ${displayClauseId(clause.clause_id)}`}
      >
        Bằng chứng
      </button>
    </div>
  );
}

function ClauseDetailPanel({
  clause,
  onOpen,
  onOpenEvidence,
  review,
  comments,
  canEdit,
  reviewing,
  commenting,
  onReviewChange,
  onCommentCreate,
  onCommentUpdate,
  onCommentDelete,
}: {
  clause: ContractClauseResult | null;
  onOpen: () => void;
  onOpenEvidence: (evidenceId?: string | null) => void;
  review?: ReviewMap | null;
  comments?: ComparisonComment[] | null;
  canEdit: boolean;
  reviewing: boolean;
  commenting?: boolean;
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
  if (!clause) {
    return (
      <div
        id="clause-detail-panel"
        className="rounded-md border border-dashed border-border-default px-4 py-8 text-center text-body-sm text-tertiary"
      >
        Chọn một điều khoản để mở đối chiếu V1 / V2.
      </div>
    );
  }

  const status = String(clause.status).toUpperCase();
  const risk = clauseRiskLevel(clause);
  const analysis = explanationText(clause);
  const diffs = clause.exact_differences ?? [];
  const evState = evidenceState(clause);

  return (
    <article
      id="clause-detail-panel"
      className="rounded-md border border-border-default bg-surface p-4"
      aria-labelledby="clause-detail-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 id="clause-detail-heading" className="text-body-sm font-semibold text-primary">
            Điều {displayClauseId(clause.clause_id)}
          </h4>
          <p className="mt-0.5 text-caption text-tertiary">{clauseStatusCaption(status)}</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge status={status} />
          <RiskBadge level={risk} />
          <EvidenceStateBadge state={evState} />
          <ReviewBadge status={reviewState(review, clause.clause_id)} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex h-9 items-center rounded-md border border-border-default px-3 text-caption font-medium text-secondary hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
        >
          Mở đối chiếu V1 / V2
        </button>
        <button
          type="button"
          onClick={() => onOpenEvidence()}
          className="inline-flex h-9 items-center rounded-md border border-border-default px-3 text-caption font-medium text-secondary hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
        >
          Xem bằng chứng
        </button>
      </div>
      <div className="mt-4">
        <ComparisonReviewActions
          clauseId={clause.clause_id}
          review={review}
          canEdit={canEdit}
          saving={reviewing}
          onChange={(status) => onReviewChange?.(clause.clause_id, status)}
        />
      </div>

      <div className="mt-4">
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
      </div>

      {risk ? (
        <p className="mt-2 text-caption text-secondary">{riskLevelHelp(risk)}</p>
      ) : null}

      {diffs.length > 0 ? (
        <div className="mt-4">
          <h5 className="text-caption font-semibold uppercase tracking-wide text-tertiary">
            Khác biệt chính xác
          </h5>
          <ul className="mt-2 flex flex-col gap-2">
            {diffs.map((row, index) => {
              const formatted = formatExactDifference(row);
              return (
                <li
                  key={`${formatted.label}-${index}`}
                  className="rounded-md border border-border-default bg-elevated/50 px-3 py-2"
                >
                  <p className="text-caption font-medium text-secondary">{formatted.label}</p>
                  <p className="mt-1 text-body-sm text-primary">
                    {formatted.oldDisplay}
                    <span className="mx-1.5 text-tertiary">→</span>
                    {formatted.newDisplay}
                  </p>
                  {formatted.delta || formatted.percent ? (
                    <p className="mt-0.5 text-caption text-secondary">
                      {[formatted.delta, formatted.percent].filter(Boolean).join(" · ")}
                    </p>
                  ) : null}
                  <div className="mt-2">
                    <ComparisonComments
                      clauseId={clause.clause_id}
                      comments={comments}
                      canEdit={canEdit}
                      saving={commenting}
                      compact
                      targetType="EXACT_DIFFERENCE"
                      targetId={exactDifferenceTargetId(index)}
                      onCreate={(body, targetType, targetId) =>
                        onCommentCreate?.(clause.clause_id, body, targetType, targetId)
                      }
                      onUpdate={(commentId, body) => onCommentUpdate?.(commentId, body)}
                      onDelete={(commentId) => onCommentDelete?.(commentId)}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <ClauseTextColumn
          label="V1"
          emptyLabel={status === "ADDED" ? "Không có ở V1" : "Không có nội dung V1"}
          text={clause.v1_text}
        />
        <ClauseTextColumn
          label="V2"
          emptyLabel={status === "REMOVED" ? "Đã xoá khỏi V2" : "Không có nội dung V2"}
          text={clause.v2_text}
        />
      </div>

      {analysis ? (
        <div className="mt-4 rounded-md border border-border-default bg-elevated/40 px-3 py-2.5">
          <p className="text-caption font-semibold uppercase tracking-wide text-tertiary">
            Phân tích AI
          </p>
          <p className="mt-1 text-body-sm text-secondary">{analysis}</p>
          {aiCitationRefs(clause).length > 0 ? (
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Trích dẫn trong phân tích AI">
              {aiCitationRefs(clause).map((citation) => (
                <li key={citation.evidenceId}>
                  <button
                    type="button"
                    onClick={() => onOpenEvidence(citation.evidenceId)}
                    className="inline-flex items-center rounded-sm border border-border-default px-1.5 py-0.5 font-mono text-caption text-secondary hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
                    aria-label={`Mở bằng chứng nguồn ${citation.index}`}
                  >
                    [{citation.index}]
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="mt-1 text-caption text-tertiary">
            Đây là diễn giải, không phải sự kiện pháp lý đã xác minh độc lập.
          </p>
        </div>
      ) : null}

      <div className="mt-4">
        <h5 className="text-caption font-semibold uppercase tracking-wide text-tertiary">
          Bằng chứng
        </h5>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          {status !== "ADDED" ? (
            <EvidenceList
              label="V1"
              items={evidenceForSide(clause, "OLD")}
              onOpenItem={onOpenEvidence}
            />
          ) : (
            <p className="text-caption text-tertiary">Thêm ở V2 — bằng chứng V1 không áp dụng.</p>
          )}
          {status !== "REMOVED" ? (
            <EvidenceList
              label="V2"
              items={evidenceForSide(clause, "NEW")}
              onOpenItem={onOpenEvidence}
            />
          ) : (
            <p className="text-caption text-tertiary">Đã xoá khỏi V2 — bằng chứng V2 không áp dụng.</p>
          )}
        </div>
      </div>
    </article>
  );
}

function ClauseTextColumn({
  label,
  text,
  emptyLabel,
}: {
  label: string;
  text?: string | null;
  emptyLabel: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border-default bg-doc-bg px-3 py-2.5">
      <p className="text-caption font-semibold uppercase tracking-wide text-tertiary">{label}</p>
      {text ? (
        <p className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-body-sm text-doc-text">
          {excerpt(text, 1200)}
        </p>
      ) : (
        <p className="mt-2 text-body-sm text-tertiary">{emptyLabel}</p>
      )}
    </div>
  );
}

function EvidenceList({
  label,
  items,
  onOpenItem,
}: {
  label: string;
  items: ContractEvidenceRef[];
  onOpenItem: (evidenceId?: string | null) => void;
}) {
  if (items.length === 0) {
    return (
      <div>
        <p className="text-caption font-medium text-secondary">{label}</p>
        <p className="mt-1 text-caption text-tertiary">Không có bằng chứng</p>
      </div>
    );
  }
  return (
    <div>
      <p className="text-caption font-medium text-secondary">{label}</p>
      <ul className="mt-1 flex flex-col gap-1">
        {items.map((item, index) => {
          const clause = item.clause_id ? displayClauseId(item.clause_id) : null;
          const page = item.page_number ? `Trang ${item.page_number}` : null;
          const text = [clause ? `Điều ${clause}` : null, page].filter(Boolean).join(" · ") || "Xem bằng chứng";
          return (
            <li key={item.evidence_id ?? `${label}-${index}`}>
              <button
                type="button"
                onClick={() => onOpenItem(item.evidence_id ?? null)}
                className="inline-flex items-center gap-1 text-caption text-accent-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
              >
                <FileText className="h-3 w-3" aria-hidden />
                {text}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
