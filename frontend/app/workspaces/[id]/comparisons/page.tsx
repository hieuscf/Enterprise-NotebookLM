/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/comparisons)
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace multi-document comparison (FR8 / UC7).
 * Responsibilities:
 *   - Pass workspace id and optional comparison/clause query to ComparisonsView
 * Dependencies:
 *   - features/comparisons/ComparisonsView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx
 * Important Notes: ?comparison=&clause= are identifiers only — never clause text.
 * =============================================================================
 */

import { ComparisonsView } from "@/features/comparisons/ComparisonsView";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ comparison?: string; clause?: string }>;
};

export default async function ComparisonsPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const query = await searchParams;
  return (
    <ComparisonsView
      workspaceId={id}
      initialComparisonId={query.comparison ?? null}
      initialClauseId={query.clause ?? null}
    />
  );
}
