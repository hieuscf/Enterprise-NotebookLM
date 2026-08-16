/**
 * =============================================================================
 * File: ComparisonReportPreview.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Interactive Comparison Report Preview workspace (TASK-CMP-25).
 * Responsibilities:
 *   - Render pending / failed / ready states from GET report detail
 *   - Navigate sections, filter/search, inspect clause detail and evidence
 *   - Export the backend-generated file; retry failed generation
 * Dependencies:
 *   - useReportPreview, report preview components, AppShell
 * Public Exports:
 *   - ComparisonReportPreview
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/reports/[reportId]/page.tsx
 * Important Notes: Rendering layer only. Do not remap, rescore, or call an LLM.
 *   Do not download the export file merely to preview.
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Component,
  type ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";

import { displayClauseId } from "@/features/comparisons/comparison-summary";
import {
  EMPTY_REPORT_FILTERS,
  allEvidenceRows,
  collectReportClauses,
  comparisonHref,
  comparisonIdFromReport,
  emptyClauseMessage,
  executiveCounts,
  filterReportClauses,
  findClauseId,
  findDetailedClause,
  isFailedStatus,
  isPendingStatus,
  isReadyStatus,
  reportNavSections,
  reportPreviewHref,
  unwrapComparisonReport,
  type ReportPreviewFilters as PreviewFilters,
} from "@/features/reports/comparison-report-preview";
import { ReportPreviewClauseDetail } from "@/features/reports/ReportPreviewClauseDetail";
import { ReportPreviewClauseList } from "@/features/reports/ReportPreviewClauseList";
import { ReportPreviewEvidence } from "@/features/reports/ReportPreviewEvidence";
import { ReportPreviewExportMenu } from "@/features/reports/ReportPreviewExportMenu";
import { ReportPreviewFilters } from "@/features/reports/ReportPreviewFilters";
import { ReportPreviewHeader } from "@/features/reports/ReportPreviewHeader";
import { ReportPreviewNavigation } from "@/features/reports/ReportPreviewNavigation";
import { ReportPreviewOverview } from "@/features/reports/ReportPreviewOverview";
import { ReportPreviewRiskSummary } from "@/features/reports/ReportPreviewRiskSummary";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import { useReportPreview } from "@/hooks/useReportPreview";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  reportId: string;
  initialClauseId?: string | null;
};

class ReportSectionBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <p role="alert" className="text-body-sm text-secondary">
          Không hiển thị được phần này.
        </p>
      );
    }
    return this.props.children;
  }
}

export function ComparisonReportPreview({
  workspaceId,
  reportId,
  initialClauseId = null,
}: Props) {
  const { user } = useAuth();
  const router = useRouter();
  const {
    report,
    loading,
    error,
    retrying,
    exporting,
    retry,
    exportReport,
  } = useReportPreview(workspaceId, reportId);

  const [filters, setFilters] = useState<PreviewFilters>(EMPTY_REPORT_FILTERS);
  const [selectedId, setSelectedId] = useState<string | null>(initialClauseId);
  const [activeSection, setActiveSection] = useState("overview");
  const [unchangedOpen, setUnchangedOpen] = useState(false);

  const comparison = unwrapComparisonReport(report?.preview);
  const comparisonId = comparisonIdFromReport(report);
  const backComparison = comparisonHref(workspaceId, comparisonId);
  const reportsHref = `/workspaces/${workspaceId}/reports`;

  const counts = useMemo(() => executiveCounts(comparison), [comparison]);
  const sections = useMemo(() => reportNavSections(comparison), [comparison]);
  const documents = comparison?.documents ?? [];

  const visibleChanged = useMemo(
    () =>
      filterReportClauses(comparison?.changed_clauses ?? [], filters, documents),
    [comparison, documents, filters],
  );
  const visibleAdded = useMemo(
    () => filterReportClauses(comparison?.added_clauses ?? [], filters, documents),
    [comparison, documents, filters],
  );
  const visibleRemoved = useMemo(
    () =>
      filterReportClauses(comparison?.removed_clauses ?? [], filters, documents),
    [comparison, documents, filters],
  );

  const allClauses = useMemo(
    () => collectReportClauses(comparison),
    [comparison],
  );

  useEffect(() => {
    if (!comparison || !initialClauseId) return;
    const resolved = findClauseId(
      [
        ...allClauses,
        ...(comparison.detailed_clause_comparisons ?? []),
      ],
      initialClauseId,
    );
    if (resolved) setSelectedId(resolved);
  }, [allClauses, comparison, initialClauseId]);

  const detailed = findDetailedClause(comparison, selectedId);
  const evidenceRows = allEvidenceRows(comparison);

  function selectClause(clauseId: string) {
    setSelectedId(clauseId);
    const display = displayClauseId(clauseId);
    router.replace(reportPreviewHref(workspaceId, reportId, display), {
      scroll: false,
    });
    const el = document.getElementById("report-clause-detail");
    el?.scrollIntoView({ block: "nearest" });
  }

  function jumpToSection(id: string) {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleRetry() {
    const created = await retry();
    if (created) {
      router.push(`/workspaces/${workspaceId}/reports/${created.id}`);
    }
  }

  return (
    <AppShell active="reports" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-4 py-6 sm:px-6">
        <div>
          <Link
            href={reportsHref}
            className="inline-flex items-center gap-1.5 text-caption font-medium text-secondary hover:text-primary"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
            Tất cả báo cáo
          </Link>
        </div>

        {loading && !report ? (
          <div className="flex items-center gap-2 text-body-sm text-secondary">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Đang tải báo cáo…
          </div>
        ) : null}

        {error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-soft px-3 py-2.5 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}

        {report && isPendingStatus(report.status) ? (
          <PendingState title={report.title} />
        ) : null}

        {report && isFailedStatus(report.status) ? (
          <FailedState
            comparisonHref={backComparison}
            retrying={retrying}
            onRetry={() => void handleRetry()}
          />
        ) : null}

        {report && isReadyStatus(report.status) && !comparison ? (
          <ReadyWithoutPreview
            title={report.title}
            format={report.export_format}
            exporting={exporting}
            onExport={() => void exportReport()}
          />
        ) : null}

        {report && isReadyStatus(report.status) && comparison ? (
          <div className="flex flex-col gap-5">
            <ReportPreviewHeader
              report={report}
              comparison={comparison}
              comparisonHref={backComparison}
              exporting={exporting}
              onExport={() => void exportReport()}
            />

            <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)] xl:grid-cols-[14rem_minmax(0,1fr)_24rem]">
              <ReportPreviewNavigation
                sections={sections}
                activeId={activeSection}
                onSelect={jumpToSection}
              />

              <div className="min-w-0 space-y-8">
                <ReportSectionBoundary>
                  <ReportPreviewOverview counts={counts} documents={documents} />
                </ReportSectionBoundary>

                <ReportSectionBoundary>
                  <ReportPreviewRiskSummary
                    riskSummary={comparison.risk_summary}
                    onOpenClause={selectClause}
                  />
                </ReportSectionBoundary>

                <ReportPreviewFilters filters={filters} onChange={setFilters} />

                {filters.query.trim() &&
                visibleChanged.length + visibleAdded.length + visibleRemoved.length === 0 ? (
                  <p className="text-body-sm text-secondary">
                    {emptyClauseMessage("search")}
                  </p>
                ) : null}

                {(comparison.changed_clauses ?? []).length > 0 ||
                filters.status === "modified" ? (
                  <ReportSectionBoundary>
                    <ReportPreviewClauseList
                      id="changed"
                      title="Điều khoản đã sửa"
                      kind="changed"
                      clauses={visibleChanged}
                      selectedId={selectedId}
                      onSelect={selectClause}
                    />
                  </ReportSectionBoundary>
                ) : null}

                {(comparison.added_clauses ?? []).length > 0 ||
                filters.status === "added" ? (
                  <ReportSectionBoundary>
                    <ReportPreviewClauseList
                      id="added"
                      title="Điều khoản thêm mới"
                      kind="added"
                      clauses={visibleAdded}
                      selectedId={selectedId}
                      onSelect={selectClause}
                    />
                  </ReportSectionBoundary>
                ) : null}

                {(comparison.removed_clauses ?? []).length > 0 ||
                filters.status === "removed" ? (
                  <ReportSectionBoundary>
                    <ReportPreviewClauseList
                      id="removed"
                      title="Điều khoản đã xoá"
                      kind="removed"
                      clauses={visibleRemoved}
                      selectedId={selectedId}
                      onSelect={selectClause}
                    />
                  </ReportSectionBoundary>
                ) : null}

                {(counts.unchanged > 0 ||
                  (comparison.unchanged_clauses?.clause_ids ?? []).length > 0) &&
                (filters.status === "all" || filters.status === "unchanged") ? (
                  <section id="unchanged" className="scroll-mt-4">
                    <h2 className="text-h3 text-primary">Điều khoản không đổi</h2>
                    <p className="mt-1 text-body-sm text-secondary">
                      {counts.unchanged} điều khoản không thay đổi.
                    </p>
                    {(comparison.unchanged_clauses?.clause_ids ?? []).length > 0 ? (
                      <button
                        type="button"
                        onClick={() => setUnchangedOpen((open) => !open)}
                        className="mt-2 text-caption font-medium text-accent-primary hover:underline"
                        aria-expanded={unchangedOpen}
                      >
                        {unchangedOpen ? "Thu gọn" : "Xem danh sách"}
                      </button>
                    ) : null}
                    {unchangedOpen ? (
                      <ul className="mt-2 columns-2 gap-3 text-caption text-tertiary sm:columns-3">
                        {(comparison.unchanged_clauses?.clause_ids ?? []).map((id, index) =>
                          id ? (
                            <li key={`${id}-${index}`} className="break-inside-avoid">
                              {displayClauseId(id)}
                            </li>
                          ) : null,
                        )}
                      </ul>
                    ) : null}
                  </section>
                ) : null}

                {evidenceRows.length > 0 ? (
                  <section id="evidence" className="scroll-mt-4">
                    <ReportSectionBoundary>
                      <ReportPreviewEvidence
                        workspaceId={workspaceId}
                        evidence={evidenceRows}
                        heading="Bằng chứng trong báo cáo"
                      />
                    </ReportSectionBoundary>
                  </section>
                ) : null}
              </div>

              <div
                id="report-clause-detail"
                className={cn(
                  "min-h-[24rem] xl:sticky xl:top-0 xl:h-[calc(100svh-8rem)]",
                  !detailed && "hidden xl:block",
                )}
              >
                {detailed ? (
                  <ReportPreviewClauseDetail
                    workspaceId={workspaceId}
                    clause={detailed}
                    onClose={() => {
                      setSelectedId(null);
                      router.replace(reportPreviewHref(workspaceId, reportId), {
                        scroll: false,
                      });
                    }}
                  />
                ) : (
                  <p className="hidden rounded-md border border-dashed border-border-default px-3 py-6 text-center text-body-sm text-tertiary xl:block">
                    Chọn một điều khoản để xem đối chiếu V1/V2, rủi ro và bằng chứng.
                  </p>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

function PendingState({ title }: { title: string }) {
  return (
    <section
      aria-live="polite"
      className="rounded-lg border border-border-default bg-surface px-5 py-8"
    >
      <div className="flex items-center gap-2 text-caption font-medium text-warning">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Đang xử lý
      </div>
      <h1 className="mt-2 text-h2 text-primary">Đang chuẩn bị báo cáo so sánh</h1>
      <p className="mt-2 max-w-xl text-body-sm text-secondary">
        Báo cáo đang được lắp từ kết quả so sánh đã xác minh. Không có tiến độ
        phần trăm vì hệ thống chỉ cho biết trạng thái đang xử lý.
      </p>
      <p className="mt-3 text-caption text-tertiary">{title}</p>
    </section>
  );
}

function FailedState({
  comparisonHref: href,
  retrying,
  onRetry,
}: {
  comparisonHref: string | null;
  retrying: boolean;
  onRetry: () => void;
}) {
  return (
    <section className="rounded-lg border border-danger/30 bg-surface px-5 py-8">
      <h1 className="text-h2 text-primary">Không tạo được báo cáo</h1>
      <p className="mt-2 max-w-xl text-body-sm text-secondary">
        Kết quả so sánh vẫn có thể còn sẵn. Bạn có thể tạo lại báo cáo hoặc quay
        lại bản so sánh.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="inline-flex h-10 items-center rounded-md border border-border-default px-3 text-body-sm font-medium text-secondary hover:bg-elevated disabled:opacity-50"
        >
          {retrying ? "Đang tạo lại…" : "Thử lại"}
        </button>
        {href ? (
          <Link
            href={href}
            className="inline-flex h-10 items-center rounded-md px-3 text-body-sm font-medium text-accent-primary hover:underline"
          >
            Quay lại so sánh
          </Link>
        ) : null}
      </div>
    </section>
  );
}

function ReadyWithoutPreview({
  title,
  format,
  exporting,
  onExport,
}: {
  title: string;
  format: "pdf" | "docx" | "markdown";
  exporting: boolean;
  onExport: () => void;
}) {
  return (
    <section className="rounded-lg border border-border-default bg-surface px-5 py-8">
      <h1 className="text-h2 text-primary">{title}</h1>
      <p className="mt-2 max-w-xl text-body-sm text-secondary">
        Báo cáo đã sẵn sàng. Xem trước cấu trúc so sánh chỉ khả dụng khi nguồn
        là một bản so sánh hoàn tất.
      </p>
      <div className="mt-4">
        <ReportPreviewExportMenu
          format={format}
          enabled
          exporting={exporting}
          onExport={onExport}
        />
      </div>
    </section>
  );
}
