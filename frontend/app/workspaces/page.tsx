/**
 * =============================================================================
 * File: page.tsx (/workspaces)
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace list (FR1 / UC1).
 * Responsibilities:
 *   - Render WorkspaceListView (auth-gated by middleware)
 * Dependencies:
 *   - features/workspaces/WorkspaceListView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, hooks/useWorkspaces
 * Important Notes: Protected route — requires auth cookie.
 * =============================================================================
 */

import { WorkspaceListView } from "@/features/workspaces/WorkspaceListView";

export default function WorkspacesPage() {
  return <WorkspaceListView />;
}
