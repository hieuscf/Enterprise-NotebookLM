/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/reports/[reportId])
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Route entry for TASK-CMP-25 Comparison Report Preview.
 * Responsibilities:
 *   - Pass workspace/report ids and optional ?clause= deep link
 * Dependencies:
 *   - features/reports/ComparisonReportPreview
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/reports/page.tsx
 * Important Notes: Reuses the existing Reports area. ?clause= is an identifier
 *   only — never clause text.
 * =============================================================================
 */

import { ComparisonReportPreview } from "@/features/reports/ComparisonReportPreview";

type PageProps = {
  params: Promise<{ id: string; reportId: string }>;
  searchParams: Promise<{ clause?: string }>;
};

export default async function ReportPreviewPage({ params, searchParams }: PageProps) {
  const { id, reportId } = await params;
  const query = await searchParams;
  return (
    <ComparisonReportPreview
      workspaceId={id}
      reportId={reportId}
      initialClauseId={query.clause ?? null}
    />
  );
}
