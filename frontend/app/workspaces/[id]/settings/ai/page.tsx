/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: AI & Retrieval settings route.
 * Responsibilities:
 *   - Render AISettings for the workspace
 * Dependencies:
 *   - features/settings/pages/AISettings
 * Public Exports:
 *   - default AISettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/AISettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { AISettings } from "@/features/settings/pages/AISettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function AISettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <AISettings workspaceId={id} />;
}
