/**
 * =============================================================================
 * File: page.tsx (/admin)
 * Module/Service: Observability / Admin Console (Web App)
 * Layer: UI
 * Purpose: Entry route for the dedicated Admin Console — redirects to the
 *          primary admin surface.
 * Responsibilities:
 *   - Redirect `/admin` → `/admin/dashboard`
 * Dependencies:
 *   - next/navigation
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: app/admin/dashboard/page.tsx, features/admin/AdminShell
 * Important Notes: Auth is enforced by middleware; RBAC is gated inside views.
 * =============================================================================
 */

import { redirect } from "next/navigation";

export default function AdminIndexPage() {
  redirect("/admin/dashboard");
}
