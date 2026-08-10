/**
 * =============================================================================
 * File: page.tsx (/admin/usage)
 * Module/Service: Admin Usage
 * Layer: UI
 * Purpose: Display workspace-level LLM usage and cost summary.
 * Responsibilities:
 *   - Load CostSummary from admin observability API via AdminUsageView
 *   - Provide date-range filtering through URL-synced state
 * Dependencies:
 *   - features/admin/AdminUsageView
 * Public Exports:
 *   - default UsagePage
 * Database/Table: message_generations (indirectly)
 * Related Modules: Observability Module, Query Router, Chat Service
 * Important Notes: CostSummary API is the source of truth. Suspense required
 *   for useSearchParams URL state sync.
 * =============================================================================
 */

import { Suspense } from "react";

import { AdminUsageView } from "@/features/admin/AdminUsageView";

export default function AdminUsagePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-6 py-8">
          <div className="h-40 animate-pulse rounded-lg border border-border-default bg-surface" />
        </div>
      }
    >
      <AdminUsageView />
    </Suspense>
  );
}
