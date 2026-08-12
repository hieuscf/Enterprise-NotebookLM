/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/summaries)
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace document summaries (FR6 / UC5).
 * Responsibilities:
 *   - Pass workspace id (+ optional documentId query) to SummariesView
 * Dependencies:
 *   - features/summaries/SummariesView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { SummariesView } from "@/features/summaries/SummariesView";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ documentId?: string }>;
};

export default async function SummariesPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { documentId } = await searchParams;
  return (
    <SummariesView workspaceId={id} initialDocumentId={documentId ?? null} />
  );
}
