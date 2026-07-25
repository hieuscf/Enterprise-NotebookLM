/**
 * =============================================================================
 * File: route.ts (POST /api/auth/logout)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Clear httpOnly auth cookies and end the browser session.
 * Responsibilities:
 *   - Delete access + refresh cookies
 * Dependencies:
 *   - lib/auth/cookies
 * Public Exports:
 *   - POST
 * Database/Table: N/A
 * Related Modules: app/logout/page.tsx
 * Important Notes: Stateless JWT — logout is cookie clearance only (Step 1 store).
 * =============================================================================
 */

import { NextResponse } from "next/server";

import { clearAuthCookies } from "@/lib/auth/cookies";

export async function POST() {
  await clearAuthCookies();
  return NextResponse.json({ ok: true });
}
