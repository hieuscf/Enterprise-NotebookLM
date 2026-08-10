/**
 * =============================================================================
 * File: useAdminSystemHealth.ts
 * Module/Service: Observability Module (Web App) — FR13
 * Layer: UI
 * Purpose: Load GET /admin/health for the System Health console.
 * Responsibilities:
 *   - Fetch SystemHealth; expose loading/error/reload
 *   - Keep previous data during refresh (no blank flash)
 * Dependencies:
 *   - lib/admin.api.getAdminSystemHealth
 * Public Exports:
 *   - useAdminSystemHealth
 * Database/Table: N/A
 * Related Modules: features/admin/AdminHealthView
 * Important Notes: Manual refresh only — no default polling.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getAdminSystemHealth } from "@/lib/admin.api";
import { ApiClientError } from "@/lib/api-client";
import type { SystemHealth } from "@/types/admin";

export function useAdminSystemHealth() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const requestId = useRef(0);
  const hasDataRef = useRef(false);

  const reload = useCallback(async () => {
    const id = ++requestId.current;
    const keepPrevious = hasDataRef.current;
    if (keepPrevious) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const data = await getAdminSystemHealth();
      if (id !== requestId.current) return;
      setHealth(data);
      hasDataRef.current = true;
      setLastUpdatedAt(Date.now());
    } catch (err) {
      if (id !== requestId.current) return;
      if (!keepPrevious) {
        setHealth(null);
        hasDataRef.current = false;
      }
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Unable to load system health.",
      );
    } finally {
      if (id === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return {
    health,
    loading,
    refreshing,
    error,
    lastUpdatedAt,
    reload,
  };
}
