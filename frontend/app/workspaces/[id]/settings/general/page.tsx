/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: General settings route.
 * Responsibilities:
 *   - Render GeneralSettings for the workspace
 * Dependencies:
 *   - features/settings/pages/GeneralSettings
 * Public Exports:
 *   - default GeneralSettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/GeneralSettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { GeneralSettings } from "@/features/settings/pages/GeneralSettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function GeneralSettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <GeneralSettings workspaceId={id} />;
}
