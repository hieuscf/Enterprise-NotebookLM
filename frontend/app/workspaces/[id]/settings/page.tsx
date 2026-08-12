/**
 * =============================================================================
 * File: page.tsx
 * Module/Service: Settings (Web App)
 * Layer: Presentation
 * Purpose: Redirect /workspaces/[id]/settings → /settings/general.
 * Responsibilities:
 *   - Canonical default Settings section
 * Dependencies:
 *   - next/navigation
 * Public Exports:
 *   - default SettingsIndexPage
 * Database/Table: N/A
 * Related Modules: features/settings/*
 * Important Notes: Workspace-scoped routing matches App Router conventions.
 * =============================================================================
 */

import { redirect } from "next/navigation";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function SettingsIndexPage({ params }: PageProps) {
  const { id } = await params;
  redirect(`/workspaces/${id}/settings/general`);
}
