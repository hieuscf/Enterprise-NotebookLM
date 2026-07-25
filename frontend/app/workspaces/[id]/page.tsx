/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id])
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace detail + edit/delete (FR1).
 * Responsibilities:
 *   - Pass route param to WorkspaceDetailView
 * Dependencies:
 *   - features/workspaces/WorkspaceDetailView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, hooks/useWorkspaceRole
 * Important Notes: Admin-only edit/delete controls; backend still enforces RBAC.
 * =============================================================================
 */

import { WorkspaceDetailView } from "@/features/workspaces/WorkspaceDetailView";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function WorkspaceDetailPage({ params }: PageProps) {
  const { id } = await params;
  return <WorkspaceDetailView workspaceId={id} />;
}
