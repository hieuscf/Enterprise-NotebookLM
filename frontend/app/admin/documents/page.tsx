/**
 * =============================================================================
 * File: page.tsx (/admin/documents)
 * Module/Service: Admin Document Management (Web App) — FR2 / FR12
 * Layer: UI
 * Purpose: Route entry for the Global Document Operations Console.
 * Responsibilities:
 *   - Render AdminDocumentsView (auth via middleware; Manage via layout/view)
 * Dependencies:
 *   - features/admin/AdminDocumentsView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, features/admin/AdminShell.tsx
 * Important Notes: Suspense required for useSearchParams URL state sync.
 * =============================================================================
 */

import { Suspense } from "react";

import { AdminDocumentsView } from "@/features/admin/AdminDocumentsView";

export default function AdminDocumentsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-6 py-8">
          <div className="h-40 animate-pulse rounded-lg border border-border-default bg-surface" />
        </div>
      }
    >
      <AdminDocumentsView />
    </Suspense>
  );
}
