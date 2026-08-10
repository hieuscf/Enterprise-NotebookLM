/**
 * =============================================================================
 * File: loading.tsx (/admin/health)
 * Module/Service: Admin Health
 * Layer: UI
 * Purpose: Route-level skeleton while the health page chunk loads.
 * Responsibilities:
 *   - Show header + overall + service card placeholders
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - default loading UI
 * Database/Table: N/A
 * Related Modules: app/admin/health/page.tsx
 * Important Notes: Matches Scholarly Precision surfaces used by the page.
 * =============================================================================
 */

export default function AdminHealthLoading() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
      <div className="space-y-2">
        <div className="h-3 w-28 animate-pulse rounded bg-elevated" />
        <div className="h-8 w-48 animate-pulse rounded bg-elevated" />
        <div className="h-4 w-96 max-w-full animate-pulse rounded bg-elevated" />
      </div>
      <div className="h-32 animate-pulse rounded-lg border border-border-default bg-surface" />
      <div className="grid gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-border-default bg-surface"
          />
        ))}
      </div>
    </div>
  );
}
