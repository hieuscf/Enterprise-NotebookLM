/**
 * =============================================================================
 * File: AdminHealthServiceGrid.tsx
 * Module/Service: Observability / System Health Console (Web App) — FR13
 * Layer: UI
 * Purpose: Core + AI/retrieval service card grids.
 * Responsibilities:
 *   - Render category sections from SystemHealth.services
 *   - Skeleton placeholders while loading
 * Dependencies:
 *   - AdminHealthServiceCard, admin-health.groupHealthServices
 * Public Exports:
 *   - AdminHealthServiceGrid
 * Database/Table: N/A
 * Related Modules: AdminHealthView
 * Important Notes: Only render services returned by the API.
 * =============================================================================
 */

"use client";

import { groupHealthServices } from "@/features/admin/admin-health";
import { AdminHealthServiceCard } from "@/features/admin/AdminHealthServiceCard";
import type { HealthService } from "@/types/admin";

type Props = {
  services: HealthService[];
  loading: boolean;
  nowTick: number;
  onOpen: (service: HealthService) => void;
};

function SectionSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={`Loading ${label}`}>
      <div className="mb-3 h-5 w-40 animate-pulse rounded bg-elevated" />
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

export function AdminHealthServiceGrid({
  services,
  loading,
  nowTick,
  onOpen,
}: Props) {
  if (loading && services.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <SectionSkeleton label="core infrastructure" />
        <SectionSkeleton label="AI and retrieval services" />
      </div>
    );
  }

  const { core, ai } = groupHealthServices(services);

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="health-core-heading">
        <h2 id="health-core-heading" className="mb-3 text-h3 text-primary">
          Core Infrastructure
        </h2>
        {core.length === 0 ? (
          <p className="text-body-sm text-tertiary">
            No core infrastructure services reported.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {core.map((svc) => (
              <AdminHealthServiceCard
                key={svc.id}
                service={svc}
                nowTick={nowTick}
                onOpen={onOpen}
              />
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="health-ai-heading">
        <h2 id="health-ai-heading" className="mb-3 text-h3 text-primary">
          AI &amp; Retrieval Services
        </h2>
        {ai.length === 0 ? (
          <p className="text-body-sm text-tertiary">
            No AI &amp; retrieval services reported.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {ai.map((svc) => (
              <AdminHealthServiceCard
                key={svc.id}
                service={svc}
                nowTick={nowTick}
                onOpen={onOpen}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
