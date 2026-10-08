/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/versions)
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Route entry for the workspace version catalog.
 * Responsibilities:
 *   - Pass the workspace id and optional document filter into VersionCenterView
 * Dependencies:
 *   - features/versions/VersionCenterView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx
 * Important Notes: Replaces the knowledge-graph item in the navigation bar.
 * =============================================================================
 */

import { VersionCenterView } from "@/features/versions/VersionCenterView";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ documentId?: string }>;
};

export default async function VersionsPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const query = await searchParams;
  return (
    <VersionCenterView workspaceId={id} initialDocumentId={query.documentId ?? null} />
  );
}
