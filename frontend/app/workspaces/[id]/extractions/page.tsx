/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/extractions)
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace information extraction (FR7 / UC6).
 * Responsibilities:
 *   - Pass workspace id (+ optional documentId query) to ExtractionsView
 * Dependencies:
 *   - features/extractions/ExtractionsView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { ExtractionsView } from "@/features/extractions/ExtractionsView";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ documentId?: string }>;
};

export default async function ExtractionsPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { documentId } = await searchParams;
  return (
    <ExtractionsView workspaceId={id} initialDocumentId={documentId ?? null} />
  );
}
