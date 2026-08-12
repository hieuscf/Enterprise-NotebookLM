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
};

export default async function KnowledgeGraphPage({ params }: PageProps) {
  const { id } = await params;
  return <KnowledgeGraphView workspaceId={id} />;
}
