/**
 * =============================================================================
 * File: useSettingsWorkspace.ts
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Shared loader for workspace metadata used across Settings pages.
 * Responsibilities:
 *   - Fetch GET /workspaces/{id}; expose name for layout scope badge
 * Dependencies:
 *   - lib/api-client
 * Public Exports:
 *   - useSettingsWorkspace
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Does not invent fields — Workspace OpenAPI shape only.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiClientError, getWorkspace } from "@/lib/api-client";
import type { Workspace } from "@/types/workspaces";

export function useSettingsWorkspace(workspaceId: string) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getWorkspace(workspaceId);
      setWorkspace(data);
    } catch (err) {
      setWorkspace(null);
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được thông tin Workspace.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { workspace, loading, error, reload, setWorkspace };
}
