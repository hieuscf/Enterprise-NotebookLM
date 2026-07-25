/**
 * =============================================================================
 * File: useWorkspaceMembers.ts
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Client hook to load / refresh the member list of one workspace (UC10).
 * Responsibilities:
 *   - Fetch GET /workspaces/{id}/members via BFF; expose loading / error / reload
 * Dependencies:
 *   - lib/api-client.listWorkspaceMembers
 * Public Exports:
 *   - useWorkspaceMembers
 * Database/Table: N/A
 * Related Modules: features/workspaces/WorkspaceMembersView
 * Important Notes: Returns [] (not throwing) while workspaceId is not ready.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiClientError, listWorkspaceMembers } from "@/lib/api-client";
import type { WorkspaceMember } from "@/types/workspaces";

export function useWorkspaceMembers(workspaceId: string | null | undefined) {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkspaceMembers(workspaceId);
      setMembers(data);
    } catch (err) {
      setMembers([]);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được danh sách thành viên.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { members, loading, error, reload };
}
