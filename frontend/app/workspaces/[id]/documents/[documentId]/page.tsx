/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/documents/[documentId])
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Document detail + viewer with optional Search deep-link (?chunk=).
 * Responsibilities:
 *   - Pass route + searchParams to DocumentDetailView
 * Dependencies:
 *   - features/documents/DocumentDetailView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: Search Results deep-link navigation
 * Important Notes: ?chunk= is bookmarkable; reload restores focus via ChunkNavigator.
 * =============================================================================
 */

import { DocumentDetailView } from "@/features/documents/DocumentDetailView";

type PageProps = {
  params: Promise<{ id: string; documentId: string }>;
  searchParams: Promise<{ chunk?: string; page?: string }>;
};

export default async function DocumentDetailPage({ params, searchParams }: PageProps) {
  const { id, documentId } = await params;
  const sp = await searchParams;
  const focusChunkId = sp.chunk?.trim() || null;
  const pageRaw = sp.page?.trim();
  const focusPage =
    pageRaw && /^\d+$/.test(pageRaw) ? Number.parseInt(pageRaw, 10) : null;

  return (
    <DocumentDetailView
      workspaceId={id}
      documentId={documentId}
      focusChunkId={focusChunkId}
      focusPage={focusPage}
    />
  );
}
