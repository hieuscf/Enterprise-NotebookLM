/**
 * =============================================================================
 * File: page.tsx (/admin/workspaces/[workspaceId])
 * Module/Service: Workspace Service (Web App) — FR1 Admin Console
 * Layer: UI
 * Purpose: Route entry for the admin workspace detail skeleton (navigation
 *          target from `/admin/workspaces` list). Full detail console is out
 *          of scope for the list-page task.
 * Responsibilities:
 *   - Pass workspaceId from the route into AdminWorkspaceDetailView
 * Dependencies:
 *   - features/admin/AdminWorkspaceDetailView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: app/admin/workspaces/page.tsx
 * Important Notes: Exists so list links do not 404 (Sidebar convention).
 * =============================================================================
 */

import { AdminWorkspaceDetailView } from "@/features/admin/AdminWorkspaceDetailView";

type Props = {
  params: Promise<{ workspaceId: string }>;
};

export default async function AdminWorkspaceDetailPage({ params }: Props) {
  const { workspaceId } = await params;
  return <AdminWorkspaceDetailView workspaceId={workspaceId} />;
}
