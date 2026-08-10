/**
 * =============================================================================
 * File: page.tsx (/admin/pipeline)
 * Module/Service: Observability / Pipeline Console (Web App) — FR13
 * Layer: UI
 * Purpose: Route entry for the Pipeline Observability Console.
 * Responsibilities:
 *   - Render AdminPipelineView (auth via middleware; Manage via layout/view)
 * Dependencies:
 *   - features/admin/AdminPipelineView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, features/admin/AdminShell.tsx
 * Important Notes: Suspense required for useSearchParams URL state sync.
 * =============================================================================
 */

import { Suspense } from "react";

import { AdminPipelineView } from "@/features/admin/AdminPipelineView";

export default function AdminPipelinePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-6 py-8">
          <div className="h-40 animate-pulse rounded-lg border border-border-default bg-surface" />
        </div>
      }
    >
      <AdminPipelineView />
    </Suspense>
  );
}
