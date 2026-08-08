/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/comparisons)
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace multi-document comparison (FR8 / UC7).
 * Responsibilities:
 *   - Pass workspace id to ComparisonsView
 * Dependencies:
 *   - features/comparisons/ComparisonsView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { ComparisonsView } from "@/features/comparisons/ComparisonsView";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function ComparisonsPage({ params }: PageProps) {
  const { id } = await params;
  return <ComparisonsView workspaceId={id} />;
}
