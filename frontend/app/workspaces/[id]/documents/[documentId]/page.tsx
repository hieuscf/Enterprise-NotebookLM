/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/documents/[documentId])
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Route entry for the document detail + version history page (FR2 Part 2).
 * Responsibilities:
 *   - Pass route params to DocumentDetailView
 * Dependencies:
 *   - features/documents/DocumentDetailView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/documents/page.tsx (list)
 * Important Notes: N/A
 * =============================================================================
 */

import { DocumentDetailView } from "@/features/documents/DocumentDetailView";

type PageProps = {
  params: Promise<{ id: string; documentId: string }>;
};

export default async function DocumentDetailPage({ params }: PageProps) {
  const { id, documentId } = await params;
  return <DocumentDetailView workspaceId={id} documentId={documentId} />;
}
