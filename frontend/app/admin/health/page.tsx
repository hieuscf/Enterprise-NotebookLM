/**
 * =============================================================================
 * File: page.tsx (/admin/health)
 * Module/Service: Admin Health
 * Layer: UI
 * Purpose: Display system and dependency health status.
 * Responsibilities:
 *   - Load system health status via AdminHealthView
 *   - Display overall and per-service health
 *   - Handle refresh/loading/error states
 * Dependencies:
 *   - features/admin/AdminHealthView
 * Public Exports:
 *   - default HealthPage
 * Database/Table: None directly
 * Related Modules: Admin Observability, Infrastructure Health
 * Important Notes: Do not expose secrets or infer healthy from missing data.
 *   Route is /admin/health (not /admin/heath).
 * =============================================================================
 */

import { AdminHealthView } from "@/features/admin/AdminHealthView";

export default function AdminHealthPage() {
  return <AdminHealthView />;
}
