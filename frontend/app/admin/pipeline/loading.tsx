/**
 * =============================================================================
 * File: loading.tsx (/admin/pipeline)
 * Module/Service: Observability / Pipeline Console (Web App) — FR13
 * Layer: UI
 * Purpose: Route-level skeleton while the pipeline page chunk loads.
 * Responsibilities:
 *   - Show header + overview + table placeholders (no full-page spinner)
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - default loading UI
 * Database/Table: N/A
 * Related Modules: app/admin/pipeline/page.tsx
 * Important Notes: Matches Scholarly Precision surfaces used by the page.
 * =============================================================================
 */

export default function AdminPipelineLoading() {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
      <div className="space-y-2">
        <div className="h-3 w-28 animate-pulse rounded bg-elevated" />
        <div className="h-8 w-40 animate-pulse rounded bg-elevated" />
        <div className="h-4 w-80 max-w-full animate-pulse rounded bg-elevated" />
      </div>
      <div className="h-10 animate-pulse rounded-lg border border-border-default bg-surface" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg border border-border-default bg-surface"
          />
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-lg border border-border-default bg-surface" />
    </div>
  );
}
