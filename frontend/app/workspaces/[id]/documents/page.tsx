/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/documents)
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Route entry for the document list page (FR2 Part 2).
 * Responsibilities:
 *   - Pass route param to DocumentList
 * Dependencies:
 *   - features/documents/DocumentList
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx (nav entry),
 *   app/workspaces/[id]/documents/[documentId]/page.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { DocumentList } from "@/features/documents/DocumentList";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function DocumentListPage({ params }: PageProps) {
  const { id } = await params;
  return <DocumentList workspaceId={id} />;
}
