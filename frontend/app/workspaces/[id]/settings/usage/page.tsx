/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: Usage & Cost settings route (Platform Manage).
 * Responsibilities:
 *   - Render UsageSettings for the workspace
 * Dependencies:
 *   - features/settings/pages/UsageSettings
 * Public Exports:
 *   - default UsageSettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/UsageSettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { UsageSettings } from "@/features/settings/pages/UsageSettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function UsageSettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <UsageSettings workspaceId={id} />;
}
