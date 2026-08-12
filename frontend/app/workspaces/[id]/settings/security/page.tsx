/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: Security settings route.
 * Responsibilities:
 *   - Render SecuritySettings for the workspace
 * Dependencies:
 *   - features/settings/pages/SecuritySettings
 * Public Exports:
 *   - default SecuritySettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/SecuritySettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { SecuritySettings } from "@/features/settings/pages/SecuritySettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function SecuritySettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <SecuritySettings workspaceId={id} />;
}
