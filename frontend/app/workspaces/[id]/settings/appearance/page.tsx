/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: Appearance settings route.
 * Responsibilities:
 *   - Render AppearanceSettings for the workspace
 * Dependencies:
 *   - features/settings/pages/AppearanceSettings
 * Public Exports:
 *   - default AppearanceSettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/AppearanceSettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { AppearanceSettings } from "@/features/settings/pages/AppearanceSettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function AppearanceSettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <AppearanceSettings workspaceId={id} />;
}
