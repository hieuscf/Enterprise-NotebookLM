/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/members)
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace member management (FR1 / UC10).
 * Responsibilities:
 *   - Pass route param to WorkspaceMembersView
 * Dependencies:
 *   - features/workspaces/WorkspaceMembersView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, hooks/useWorkspaceRole
 * Important Notes: Admin-only mutations; backend still enforces RBAC.
 * =============================================================================
 */

import { WorkspaceMembersView } from "@/features/workspaces/WorkspaceMembersView";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function WorkspaceMembersPage({ params }: PageProps) {
  const { id } = await params;
  return <WorkspaceMembersView workspaceId={id} />;
}
