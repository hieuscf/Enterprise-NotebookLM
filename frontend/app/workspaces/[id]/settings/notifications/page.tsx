/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: Notification settings route.
 * Responsibilities:
 *   - Render NotificationSettings for the workspace
 * Dependencies:
 *   - features/settings/pages/NotificationSettings
 * Public Exports:
 *   - default NotificationSettingsPage
 * Database/Table: N/A
 * Related Modules: features/settings/pages/NotificationSettings.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { NotificationSettings } from "@/features/settings/pages/NotificationSettings";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function NotificationSettingsPage({ params }: PageProps) {
  const { id } = await params;
  return <NotificationSettings workspaceId={id} />;
}
