/**
 * =============================================================================
 * File: loading.tsx (/admin/usage)
 * Module/Service: Admin Usage
 * Layer: UI
 * Purpose: Route-level skeleton while the usage page chunk loads.
 * Responsibilities:
 *   - Show header + date range + KPI + panel placeholders
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - default loading UI
 * Database/Table: N/A
 * Related Modules: app/admin/usage/page.tsx
 * Important Notes: Matches Scholarly Precision surfaces used by the page.
 * =============================================================================
 */

export default function AdminUsageLoading() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
      <div className="space-y-2">
        <div className="h-3 w-24 animate-pulse rounded bg-elevated" />
        <div className="h-8 w-28 animate-pulse rounded bg-elevated" />
        <div className="h-4 w-96 max-w-full animate-pulse rounded bg-elevated" />
      </div>
      <div className="h-28 animate-pulse rounded-lg border border-border-default bg-surface" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg border border-border-default bg-surface"
          />
        ))}
      </div>
      <div className="h-40 animate-pulse rounded-lg border border-border-default bg-surface" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-56 animate-pulse rounded-lg border border-border-default bg-surface" />
        <div className="h-56 animate-pulse rounded-lg border border-border-default bg-surface" />
      </div>
    </div>
  );
}
