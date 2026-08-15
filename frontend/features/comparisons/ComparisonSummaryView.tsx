/**
 * =============================================================================
 * File: ComparisonSummaryView.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TASK-CMP-17 clause-level Comparison Summary for CMP-15/16 reports.
 * Responsibilities:
 *   - Header V1 vs V2, status, summary stats, risk, distribution, priority
 *   - Filterable clause list; open CMP-18 side-by-side workspace
 * Dependencies:
 *   - comparison-summary helpers, ClauseComparisonView, design tokens
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
  Search,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ClauseComparisonView } from "@/features/comparisons/ClauseComparisonView";
import {
  EvidenceStateBadge,
  RiskBadge,
  StatusBadge,
  riskToneClass,
} from "@/features/comparisons/comparison-badges";
import { clauseNav, resolveClauseId } from "@/features/comparisons/clause-view";
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
  evidenceViewerHref,
  excerpt,
  explanationText,
  filterClauses,
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
  type ClauseFilter,
} from "@/features/comparisons/comparison-summary";
import { formatComparisonDateTime } from "@/features/comparisons/comparison-format";
import { cn } from "@/lib/utils";
import type {
  Comparison,
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
  onClauseChange?: (clauseId: string | null) => void;
};

const FILTERS: { id: ClauseFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "modified", label: "Đã sửa" },
  { id: "added", label: "Thêm mới" },
  { id: "removed", label: "Đã xoá" },
  { id: "unchanged", label: "Không đổi" },
];

const RISK_FILTERS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

export function ComparisonSummaryView({
  workspaceId,
  comparison,
  report,
  documentMeta = {},
  initialClauseId = null,
  onClauseChange,
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

  const [filter, setFilter] = useState<ClauseFilter>("all");
  const [riskFilter, setRiskFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
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

  useEffect(() => {
    const resolved = resolveClauseId(clauses, initialClauseId);
    if (!resolved) return;
    setSelectedId(resolved);
    setWorkspaceOpen(true);
  }, [clauses, initialClauseId]);

  const visible = useMemo(
    () => filterClauses(clauses, filter, query, riskFilter),
    [clauses, filter, query, riskFilter],
  );
  const selected = clauses.find((c) => c.clause_id === selectedId) ?? null;
  const nav = clauseNav(visible, selectedId);
  const showRiskFilters = risks.critical + risks.high + risks.medium + risks.low > 0;
  const noMaterial = summary ? !hasMaterialChanges(summary) : false;

  function openClause(clauseId: string) {
    setSelectedId(clauseId);
    setWorkspaceOpen(true);
    onClauseChange?.(clauseId);
  }

  function closeWorkspace() {
    setWorkspaceOpen(false);
    onClauseChange?.(null);
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
            <StatCard label="Điều khoản" value={summary.total_clauses} emphasize="quiet" />
            <StatCard label="Không đổi" value={summary.unchanged} emphasize="quiet" />
            <StatCard label="Đã sửa" value={summary.modified} emphasize="modified" />
            <StatCard label="Thêm mới" value={summary.added} emphasize="added" />
            <StatCard label="Đã xoá" value={summary.removed} emphasize="removed" />
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
          <RiskCountCard level="CRITICAL" count={risks.critical} />
          <RiskCountCard level="HIGH" count={risks.high} />
          <RiskCountCard level="MEDIUM" count={risks.medium} />
          <RiskCountCard level="LOW" count={risks.low} />
        </div>
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
                  onOpen={() => openClause(clause.clause_id)}
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
        <div className="flex flex-col gap-2">
          <div
            role="tablist"
            aria-label="Lọc theo trạng thái điều khoản"
            className="flex flex-wrap gap-1.5"
          >
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={filter === item.id}
                onClick={() => setFilter(item.id)}
                className={cn(
                  "rounded-md border px-2.5 py-1 text-caption font-medium",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                  filter === item.id
                    ? "border-accent-primary/40 bg-accent-primary/10 text-primary"
                    : "border-border-default text-secondary hover:bg-elevated",
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
          {showRiskFilters ? (
            <div
              role="group"
              aria-label="Lọc theo mức rủi ro"
              className="flex flex-wrap gap-1.5"
            >
              {RISK_FILTERS.map((level) => (
                <button
                  key={level}
                  type="button"
                  aria-pressed={riskFilter === level}
                  onClick={() => setRiskFilter((prev) => (prev === level ? null : level))}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-caption font-medium",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                    riskFilter === level
                      ? riskToneClass(level)
                      : "border-border-default text-secondary hover:bg-elevated",
                  )}
                >
                  {riskLevelLabel(level)}
                </button>
              ))}
            </div>
          ) : null}
          <label className="relative block">
            <span className="sr-only">Tìm điều khoản</span>
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-tertiary"
              aria-hidden
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Tìm số điều, tiêu đề hoặc nội dung…"
              className="h-9 w-full rounded-md border border-border-default bg-surface pl-8 pr-3 text-body-sm text-primary placeholder:text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
            />
          </label>
        </div>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <ul
            className="flex max-h-[32rem] flex-col gap-1 overflow-y-auto pr-0.5"
            aria-label="Danh sách điều khoản"
          >
            {visible.length === 0 ? (
              <li className="rounded-md border border-dashed border-border-default px-3 py-4 text-body-sm text-tertiary">
                Không có điều khoản khớp bộ lọc.
              </li>
            ) : (
              visible.map((clause) => (
                <li key={clause.clause_id}>
                  <ClauseRow
                    clause={clause}
                    selected={selectedId === clause.clause_id}
                    onSelect={() => openClause(clause.clause_id)}
                  />
                </li>
              ))
            )}
          </ul>
          <ClauseDetailPanel
            clause={selected}
            workspaceId={workspaceId}
            report={report}
            onOpen={() => selected && openClause(selected.clause_id)}
          />
        </div>
      </section>

      <ClauseComparisonView
        open={workspaceOpen}
        workspaceId={workspaceId}
        report={report}
        clause={selected}
        nav={nav}
        filter={filter}
        error={
          workspaceOpen && initialClauseId && !resolveClauseId(clauses, initialClauseId) && !selected
            ? "Không tải được đối chiếu điều khoản này."
            : null
        }
        documentMeta={documentMeta}
        onClose={closeWorkspace}
        onPrev={() => nav.prevId && openClause(nav.prevId)}
        onNext={() => nav.nextId && openClause(nav.nextId)}
        onRetry={
          initialClauseId
            ? () => {
                const resolved = resolveClauseId(clauses, initialClauseId);
                if (resolved) openClause(resolved);
              }
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
}: {
  label: string;
  value: number;
  emphasize: "quiet" | "modified" | "added" | "removed";
}) {
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2.5",
        emphasize === "quiet" && "border-border-default bg-elevated/40",
        emphasize === "modified" && "border-warning/30 bg-warning/5",
        emphasize === "added" && "border-info/30 bg-info/5",
        emphasize === "removed" && "border-danger/30 bg-danger-soft",
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
    </div>
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

function RiskCountCard({ level, count }: { level: string; count: number }) {
  const label = riskLevelLabel(level);
  const help = riskLevelHelp(level);
  return (
    <div className={cn("rounded-md border px-3 py-2.5", riskToneClass(level))}>
      <p className="text-caption font-semibold uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-h3 tabular-nums text-primary">{count}</p>
      <p className="mt-1 text-caption text-secondary">{help}</p>
    </div>
  );
}

function PriorityChangeCard({
  clause,
  selected,
  onOpen,
}: {
  clause: ContractClauseResult;
  selected: boolean;
  onOpen: () => void;
}) {
  const risk = clauseRiskLevel(clause);
  const analysis = explanationText(clause);
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-pressed={selected}
      className={cn(
        "w-full rounded-md border px-3 py-3 text-left",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
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
      <span className="sr-only">Mở chi tiết điều khoản {displayClauseId(clause.clause_id)}</span>
    </button>
  );
}

function ClauseRow({
  clause,
  selected,
  onSelect,
}: {
  clause: ContractClauseResult;
  selected: boolean;
  onSelect: () => void;
}) {
  const status = String(clause.status).toUpperCase();
  const quiet = status === "UNCHANGED";
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-expanded={selected}
      aria-controls="clause-detail-panel"
      className={cn(
        "w-full rounded-md border px-3 py-2 text-left",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
        selected
          ? "border-accent-primary/40 bg-accent-primary/5"
          : quiet
            ? "border-transparent bg-transparent hover:bg-elevated"
            : "border-border-default bg-surface hover:bg-elevated",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={cn("text-body-sm font-medium", quiet ? "text-secondary" : "text-primary")}>
          {displayClauseId(clause.clause_id)}
        </span>
        <StatusBadge status={status} />
        <RiskBadge level={clauseRiskLevel(clause)} />
      </div>
      <p className={cn("mt-1 text-caption", quiet ? "text-tertiary" : "text-secondary")}>
        {shortChangeSummary(clause)}
      </p>
      <p className="mt-0.5 text-caption text-tertiary">{evidenceLine(clause)}</p>
    </button>
  );
}

function ClauseDetailPanel({
  clause,
  workspaceId,
  report,
  onOpen,
}: {
  clause: ContractClauseResult | null;
  workspaceId: string;
  report: ContractComparisonReport;
  onOpen: () => void;
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
  const v1Doc = report.metadata?.document_v1;
  const v2Doc = report.metadata?.document_v2;

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
        </div>
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="mt-3 inline-flex h-9 items-center rounded-md border border-border-default px-3 text-caption font-medium text-secondary hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
      >
        Mở đối chiếu V1 / V2
      </button>

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
              workspaceId={workspaceId}
              fallbackDocumentId={v1Doc?.document_id}
              fallbackVersionId={v1Doc?.document_version_id}
            />
          ) : (
            <p className="text-caption text-tertiary">Thêm ở V2 — bằng chứng V1 không áp dụng.</p>
          )}
          {status !== "REMOVED" ? (
            <EvidenceList
              label="V2"
              items={evidenceForSide(clause, "NEW")}
              workspaceId={workspaceId}
              fallbackDocumentId={v2Doc?.document_id}
              fallbackVersionId={v2Doc?.document_version_id}
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
  workspaceId,
  fallbackDocumentId,
  fallbackVersionId,
}: {
  label: string;
  items: ContractEvidenceRef[];
  workspaceId: string;
  fallbackDocumentId?: string | null;
  fallbackVersionId?: string | null;
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
          const href = evidenceViewerHref(
            workspaceId,
            item,
            fallbackDocumentId,
            fallbackVersionId,
          );
          const clause = item.clause_id ? displayClauseId(item.clause_id) : null;
          const page = item.page_number ? `Trang ${item.page_number}` : null;
          const text = [clause ? `Điều ${clause}` : null, page].filter(Boolean).join(" · ") || "Mở nguồn";
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
    </div>
  );
}
