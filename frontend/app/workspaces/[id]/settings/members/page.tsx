/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: Members & Access settings route.
 * Responsibilities:
 *   - Render MembersSettings for the workspace
 * Dependencies:
 *   - features/settings/pages/MembersSettings
 * Public Exports:
 *   - default MembersSettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/MembersSettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { MembersSettings } from "@/features/settings/pages/MembersSettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function MembersSettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <MembersSettings workspaceId={id} />;
}
