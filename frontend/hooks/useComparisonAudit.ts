/**
 * =============================================================================
 * File: useComparisonAudit.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Load and refresh TASK-CMP-23 comparison audit trail.
 * Responsibilities:
 *   - GET audit on comparison change
 *   - POST CLAUSE_OPENED without blocking the clause workspace
 * Dependencies:
 *   - lib/comparisons.api
 * Public Exports:
 *   - useComparisonAudit
 * Database/Table: N/A
 * Related Modules: ComparisonsView
 * Important Notes: Failures to record an open must not prevent viewing a clause.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getComparisonAudit,
  recordComparisonClauseOpened,
} from "@/lib/comparisons.api";
import type { ComparisonAuditEvent } from "@/types/comparisons";

export function useComparisonAudit(
  workspaceId: string,
  comparisonId: string | null,
) {
  const [events, setEvents] = useState<ComparisonAuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    if (!comparisonId) {
      setEvents([]);
      return;
    }
    setLoading(true);
    try {
      const trail = await getComparisonAudit(workspaceId, comparisonId);
      if (!mountedRef.current) return;
      setEvents(Array.isArray(trail.events) ? trail.events : []);
    } catch {
      if (mountedRef.current) setEvents([]);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [comparisonId, workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const recordOpened = useCallback(
    async (clauseId: string) => {
      if (!comparisonId || !clauseId.trim()) return;
      try {
        const trail = await recordComparisonClauseOpened(
          workspaceId,
          comparisonId,
          clauseId,
        );
        if (!mountedRef.current) return;
        setEvents(Array.isArray(trail.events) ? trail.events : []);
      } catch {
        // Opening a clause must still succeed if the audit write fails.
      }
    },
    [comparisonId, workspaceId],
  );

  return { events, loading, reload, recordOpened };
}
