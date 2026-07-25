/**
 * =============================================================================
 * File: index.ts
 * Module/Service: Web App
 * Layer: UI
 * Purpose: Shared TypeScript types aligned with OpenAPI schemas.
 * Responsibilities:
 *   - Hold frontend type definitions matching backend Pydantic/OpenAPI models
 * Dependencies:
 *   - docs/Enterprise notebooklm openapi.yaml
 * Public Exports:
 *   - HealthResponse
 * Database/Table: N/A
 * Related Modules: frontend/lib/api-client.ts
 * Important Notes: Phase 1.1 skeleton — expand as OpenAPI schemas are used.
 * =============================================================================
 */

export type HealthResponse = {
  status: string;
};

export type {
  AuthToken,
  User,
  WorkspaceMembership,
  WorkspaceRole,
} from "./auth";
