/**
 * =============================================================================
 * File: page.tsx (/admin/query-logs)
 * Module/Service: Observability / Query Logs Console (Web App) — FR13
 * Layer: UI
 * Purpose: Route entry for the Query Router Observability console.
 * Responsibilities:
 *   - Render AdminQueryLogsView (auth via middleware; Manage via layout/view)
 * Dependencies:
 *   - features/admin/AdminQueryLogsView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, features/admin/AdminShell.tsx
 * Important Notes: Suspense required for useSearchParams URL state sync.
 *   Query logs are read-only audit data.
 * =============================================================================
 */

import { Suspense } from "react";

import { AdminQueryLogsView } from "@/features/admin/AdminQueryLogsView";

export default function AdminQueryLogsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-6 py-8">
          <div className="h-40 animate-pulse rounded-lg border border-border-default bg-surface" />
        </div>
      }
    >
      <AdminQueryLogsView />
    </Suspense>
  );
}
