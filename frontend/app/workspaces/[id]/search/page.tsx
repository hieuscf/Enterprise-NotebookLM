/**
 * =============================================================================
 * File: page.tsx (/workspaces/[id]/search)
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Route entry for workspace Intelligent Search (FR3 / UC3).
 * Responsibilities:
 *   - Pass workspace id to SearchView
 * Dependencies:
 *   - features/search/SearchView
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: features/shell/Sidebar.tsx
 * Important Notes: N/A
 * =============================================================================
 */

import { SearchView } from "@/features/search/SearchView";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function SearchPage({ params }: PageProps) {
  const { id } = await params;
  return <SearchView workspaceId={id} />;
}
