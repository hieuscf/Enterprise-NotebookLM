/**
 * =============================================================================
 * File: page.tsx (/admin/workspaces)
 * Module/Service: Workspace Service (Web App) — FR1 Admin Console
 * Layer: UI
 * Purpose: Route entry for the Workspace Management Console.
 * Responsibilities:
 *   - Render AdminWorkspacesView (auth-gated by middleware; RBAC-gated inside
 *     the view per workspace-admin membership, same pattern as /admin/dashboard)
 * Dependencies:
 *   - features/admin/AdminWorkspacesView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, features/admin/AdminShell.tsx
 * Important Notes: Runs in the same Next.js app on port 3000 — dedicated
 *   AdminShell (not product AppShell).
 * =============================================================================
 */

import { AdminWorkspacesView } from "@/features/admin/AdminWorkspacesView";

export default function AdminWorkspacesPage() {
  return <AdminWorkspacesView />;
}
