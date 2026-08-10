/**
 * =============================================================================
 * File: page.tsx (/admin/users)
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Route entry for the Enterprise User & Access Management Console.
 * Responsibilities:
 *   - Render AdminUsersView (auth-gated by middleware; RBAC-gated inside
 *     the view per workspace-admin membership)
 * Dependencies:
 *   - features/admin/AdminUsersView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, features/admin/AdminShell.tsx
 * Important Notes: Same Next.js app on port 3000 — dedicated AdminShell.
 * =============================================================================
 */

import { AdminUsersView } from "@/features/admin/AdminUsersView";

export default function AdminUsersPage() {
  return <AdminUsersView />;
}
