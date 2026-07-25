/**
 * =============================================================================
 * File: useAuth.ts
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Client hook to load current user from BFF GET /api/auth/me.
 * Responsibilities:
 *   - Fetch User once on mount; expose loading / user / reload
 * Dependencies:
 *   - lib/api-client.authMe
 * Public Exports:
 *   - useAuth
 * Database/Table: N/A
 * Related Modules: hooks/useWorkspaceRole, app/(app) layout
 * Important Notes: Roles always come from /auth/me (DB), not JWT decode in browser.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { authMe } from "@/lib/api-client";
import type { User } from "@/types/auth";

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    const me = await authMe();
    setUser(me);
    setLoading(false);
    return me;
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { user, loading, reload };
}
