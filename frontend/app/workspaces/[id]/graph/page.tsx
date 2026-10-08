/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/graph)
 * Module/Service: Knowledge Graph (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace Knowledge Graph exploration.
 * Responsibilities:
 *   - Pass workspace id into KnowledgeGraphView
 * Dependencies:
 *   - features/graph/KnowledgeGraphView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx
 * Important Notes: Scoped strictly by workspace route param.
 * =============================================================================
 */

import { KnowledgeGraphView } from "@/features/graph/KnowledgeGraphView";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ documentId?: string; nodeId?: string }>;
};

export default async function KnowledgeGraphPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const query = await searchParams;
  return (
    <KnowledgeGraphView
      workspaceId={id}
      openedDocumentId={query.documentId ?? null}
      openedNodeId={query.nodeId ?? null}
    />
  );
}
