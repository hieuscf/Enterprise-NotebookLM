/**
 * =============================================================================
 * File: page.tsx (/admin/users/[userId])
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Route entry for the admin user detail skeleton (navigation target
 *          from `/admin/users` list). Full detail console is out of scope for
 *          the list-page task.
 * Responsibilities:
 *   - Pass userId from the route into AdminUserDetailView
 * Dependencies:
 *   - features/admin/AdminUserDetailView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: app/admin/users/page.tsx
 * Important Notes: Exists so list links do not 404.
 * =============================================================================
 */

import { AdminUserDetailView } from "@/features/admin/AdminUserDetailView";

type Props = {
  params: Promise<{ userId: string }>;
};

export default async function AdminUserDetailPage({ params }: Props) {
  const { userId } = await params;
  return <AdminUserDetailView userId={userId} />;
}
