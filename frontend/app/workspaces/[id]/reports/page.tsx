/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/reports)
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace report generation (FR9 / UC8).
 * Responsibilities:
 *   - Pass workspace id to ReportsView
 * Dependencies:
 *   - features/reports/ReportsView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { ReportsView } from "@/features/reports/ReportsView";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function ReportsPage({ params }: PageProps) {
  const { id } = await params;
  return <ReportsView workspaceId={id} />;
}
