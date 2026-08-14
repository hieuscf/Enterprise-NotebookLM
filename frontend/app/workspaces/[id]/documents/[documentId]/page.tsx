/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/documents/[documentId])
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Document detail + viewer with Search/Chat deep-links.
 * Responsibilities:
 *   - Pass route + searchParams (?chunk=&page=&citation=) to DocumentDetailView
 * Dependencies:
 *   - features/documents/DocumentDetailView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: Search Results, Chat citation navigation
 * Important Notes: ?citation= loads snippet from sessionStorage for highlight.
 * =============================================================================
 */

import { DocumentDetailView } from "@/features/documents/DocumentDetailView";

type PageProps = {
  params: Promise<{ id: string; documentId: string }>;
  searchParams: Promise<{
    chunk?: string;
    page?: string;
    citation?: string;
    version?: string;
    view?: string;
  }>;
};

export default async function DocumentDetailPage({ params, searchParams }: PageProps) {
  const { id, documentId } = await params;
  const sp = await searchParams;
  const focusChunkId = sp.chunk?.trim() || null;
  const focusCitationId = sp.citation?.trim() || null;
  const focusVersionId = sp.version?.trim() || null;
  const pageRaw = sp.page?.trim();
  const focusPage =
    pageRaw && /^\d+$/.test(pageRaw) ? Number.parseInt(pageRaw, 10) : null;
  const viewRaw = sp.view?.trim().toLowerCase();
  const initialView =
    viewRaw === "original" ? "original" : "knowledge";

  return (
    <DocumentDetailView
      workspaceId={id}
      documentId={documentId}
      focusChunkId={focusChunkId}
      focusPage={focusPage}
      focusCitationId={focusCitationId}
      focusVersionId={focusVersionId}
      initialView={initialView}
    />
  );
}
