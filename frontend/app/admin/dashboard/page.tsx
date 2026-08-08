/**
 * =============================================================================
 * File: page.tsx (/admin/dashboard)
 * Module/Service: Observability Module (Web App)
 * Layer: UI
 * Purpose: Route entry for the Admin Control Center / Operations Dashboard.
 * Responsibilities:
 *   - Render AdminDashboardView (auth-gated by middleware; RBAC-gated inside
 *     the view itself per-workspace admin membership)
 * Dependencies:
 *   - features/admin/AdminDashboardView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, features/admin/AdminShell.tsx
 * Important Notes: Runs in the same Next.js app on port 3000 — dedicated
 *   AdminShell (not product AppShell).
 * =============================================================================
 */

import { AdminDashboardView } from "@/features/admin/AdminDashboardView";

export default function AdminDashboardPage() {
  return <AdminDashboardView />;
}
