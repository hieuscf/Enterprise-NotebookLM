/**
 * =============================================================================
 * File: page.tsx (/logout)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Clear session cookies and redirect to /login.
 * Responsibilities:
 *   - Call POST /api/auth/logout then clear AuthProvider + navigate to login
 * Dependencies:
 *   - lib/api-client.authLogout, hooks/useAuth
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts
 * Important Notes: Client page so cookie clearance runs in browser context.
 *   Must reload AuthProvider after logout — root layout does not remount.
 * =============================================================================
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/hooks/useAuth";
import { authLogout } from "@/lib/api-client";

export default function LogoutPage() {
  const router = useRouter();
  const { reload: reloadAuth } = useAuth();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await authLogout();
      // Drop cached user from AuthProvider (layout persists across /logout → /login).
      await reloadAuth();
      if (!cancelled) {
        router.replace("/login");
        router.refresh();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadAuth, router]);

  return (
    <main className="flex h-full items-center justify-center bg-base">
      <p className="text-body text-secondary">Đang đăng xuất…</p>
    </main>
  );
}
