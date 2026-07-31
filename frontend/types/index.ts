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
 *   - HealthResponse, auth types, workspace types
 * Database/Table: N/A
 * Related Modules: frontend/lib/api-client.ts
 * Important Notes: Expand as OpenAPI schemas are used on the client.
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

export type { Citation, ContentLocation } from "./citations";

export type {
  Document,
  DocumentListResponse,
  DocumentVersion,
  DocumentVersionStatus,
  FileType,
  PipelineRun,
  PipelineStageLog,
  PipelineStageName,
  PipelineStageNameLegacy,
  PipelineStageNameV3,
  PipelineStatus,
} from "./documents";

export type {
  RetrievalMethod,
  SearchFilters,
  SearchHistoryItem,
  SearchRequest,
  SearchResultItem,
  SearchResultResponse,
} from "./search";

export type {
  AddMemberInput,
  UpdateMemberRoleInput,
  Workspace,
  WorkspaceCreateInput,
  WorkspaceListResponse,
  WorkspaceMember,
  WorkspaceUpdateInput,
} from "./workspaces";
