/**
 * =============================================================================
 * File: page.tsx (/logout)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Clear session cookies and redirect to /login.
 * Responsibilities:
 *   - Call POST /api/auth/logout then navigate to login
 * Dependencies:
 *   - lib/api-client.authLogout
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts
 * Important Notes: Client page so cookie clearance runs in browser context.
 * =============================================================================
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { authLogout } from "@/lib/api-client";

export default function LogoutPage() {
  const router = useRouter();

  useEffect(() => {
    void (async () => {
      await authLogout();
      router.replace("/login");
      router.refresh();
    })();
  }, [router]);

  return (
    <main className="flex h-full items-center justify-center bg-base">
      <p className="text-body text-secondary">Đang đăng xuất…</p>
    </main>
  );
}
