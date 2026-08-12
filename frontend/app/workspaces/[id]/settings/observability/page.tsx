/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: Observability settings route (Platform Manage).
 * Responsibilities:
 *   - Render ObservabilitySettings for the workspace
 * Dependencies:
 *   - features/settings/pages/ObservabilitySettings
 * Public Exports:
 *   - default ObservabilitySettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/ObservabilitySettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { ObservabilitySettings } from "@/features/settings/pages/ObservabilitySettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function ObservabilitySettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <ObservabilitySettings workspaceId={id} />;
}
