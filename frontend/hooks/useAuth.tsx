/**
 * =============================================================================
 * File: useAuth.tsx
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Shared client auth state from BFF GET /api/auth/me (one fetch).
 * Responsibilities:
 *   - AuthProvider: single in-flight /auth/me for the whole tree
 *   - useAuth(): expose user / loading / reload without N× duplicate calls
 * Dependencies:
 *   - lib/api-client.authMe
 * Public Exports:
 *   - AuthProvider, useAuth
 * Database/Table: N/A
 * Related Modules: hooks/useWorkspaceRole, features/shell/*, features/admin/*
 * Important Notes: Roles always come from /auth/me (DB), not JWT decode in browser.
 * =============================================================================
 */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { authMe } from "@/lib/api-client";
import type { User } from "@/types/auth";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  reload: () => Promise<User | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const me = await authMe();
      setUser(me);
      return me;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const value = useMemo(
    () => ({ user, loading, reload }),
    [user, loading, reload],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  // Fallback for rare mounts outside provider (tests / isolated stories).
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const localReload = useCallback(async () => {
    setLoading(true);
    try {
      const me = await authMe();
      setUser(me);
      return me;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ctx) return;
    void localReload();
  }, [ctx, localReload]);

  if (ctx) return ctx;
  return { user, loading, reload: localReload };
}
