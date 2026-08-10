/**
 * =============================================================================
 * File: layout.tsx
 * Module/Service: Admin Console (Web App)
 * Layer: UI
 * Purpose: Layout + Platform Manage guard for all /admin/* routes.
 * Responsibilities:
 *   - Wrap admin pages with RequireManage (platform_role === manage)
 * Dependencies:
 *   - components/auth/RequireManage
 * Public Exports:
 *   - default AdminLayout
 * Database/Table: N/A
 * Related Modules: app/admin/page.tsx and nested admin pages
 * Important Notes: Workspace Admin receives 403 UI; backend still enforces Manage.
 * =============================================================================
 */

"use client";

import type { ReactNode } from "react";

import { RequireManage } from "@/components/auth/RequireManage";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <RequireManage>{children}</RequireManage>;
}
