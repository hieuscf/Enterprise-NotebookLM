/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: Workspace settings route.
 * Responsibilities:
 *   - Render WorkspaceSettings for the workspace
 * Dependencies:
 *   - features/settings/pages/WorkspaceSettings
 * Public Exports:
 *   - default WorkspaceSettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/WorkspaceSettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { WorkspaceSettings } from "@/features/settings/pages/WorkspaceSettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function WorkspaceSettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <WorkspaceSettings workspaceId={id} />;
}
