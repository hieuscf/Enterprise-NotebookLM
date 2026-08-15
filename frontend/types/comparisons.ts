/**
 * =============================================================================
 * File: comparisons.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Comparisons API matching OpenAPI (FR8 / UC7).
 * Responsibilities:
 *   - Align Comparison / status / result with backend schema
 *   - Optional contract_comparison (CMP-15/16) for clause-level summary UI
 *   - CMP-23 audit events are fetched separately from Comparison payload
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml Comparison schema
 * Public Exports:
 *   - ComparisonStatus, ComparisonResult, Comparison, ComparisonCreateRequest
 *   - ContractComparisonReport and nested clause/evidence types
 * Database/Table: comparisons, comparison_documents
 * Related Modules: lib/comparisons.api, features/comparisons/*
 * Important Notes: result is null while processing/failed; object when completed.
 *   contract_comparison is omitted/null when clause enrichment is unavailable.
 * =============================================================================
 */

export type ComparisonStatus = "processing" | "completed" | "failed";

export type ClauseComparisonStatus =
  | "UNCHANGED"
  | "MODIFIED"
  | "ADDED"
  | "REMOVED"
  | "UNRESOLVED"
  | string;

export type RiskLevelValue =
  | "CRITICAL"
  | "HIGH"
  | "MEDIUM"
  | "LOW"
  | string;

export type VerificationStatusValue =
  | "VERIFIED"
  | "PARTIALLY_VERIFIED"
  | "UNVERIFIED"
  | "INSUFFICIENT_EVIDENCE"
  | "INVALID"
  | string;

export type ContractDocumentRef = {
  document_id?: string | null;
  document_version_id?: string | null;
  title?: string | null;
  workspace_id?: string | null;
};

export type ContractEvidenceRef = {
  evidence_id?: string | null;
  side?: string | null;
  document_id?: string | null;
  document_version_id?: string | null;
  clause_id?: string | null;
  identity_key?: string | null;
  chunk_id?: string | null;
  page_number?: number | null;
  start_offset?: number | null;
  end_offset?: number | null;
  source_type?: string | null;
  role?: string | null;
  display_text?: string | null;
};

export type ContractExactDifference = {
  change_type?: string | null;
  value_type?: string | null;
  direction?: string | null;
  old?: {
    raw?: string | null;
    value?: string | null;
    currency?: string | null;
    start?: number | null;
    end?: number | null;
  } | null;
  new?: {
    raw?: string | null;
    value?: string | null;
    currency?: string | null;
    start?: number | null;
    end?: number | null;
  } | null;
  delta?: string | null;
  relative_change_percent?: string | null;
  delta_unit?: string | null;
  context?: string | null;
  source_offset?: [number, number] | number[] | null;
  target_offset?: [number, number] | number[] | null;
  [key: string]: unknown;
};

export type ContractClauseRisk = {
  risk_category?: string | null;
  risk_level?: RiskLevelValue | null;
  risk_score?: string | number | null;
  risk_impact?: string | null;
  status?: string | null;
  triggered_rules?: string[] | null;
  reason?: string | null;
  [key: string]: unknown;
};

export type ContractClauseExplanation = {
  status?: string | null;
  reasons?: string[] | null;
  unavailable?: boolean;
  output?: {
    explanation?: string | null;
    evidence_ids?: string[] | null;
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
};

export type ContractEvidenceCheckStatus =
  | "VALID"
  | "INVALID"
  | "MISSING"
  | "MISMATCH"
  | "UNAVAILABLE"
  | string;

export type ContractEvidenceVerification = {
  evidence_id?: string | null;
  side?: string | null;
  status?: ContractEvidenceCheckStatus | null;
  reasons?: string[] | null;
};

export type ContractClauseVerification = {
  status?: VerificationStatusValue | null;
  human_message?: string | null;
  verified_evidence_ids?: string[] | null;
  invalid_evidence_ids?: string[] | null;
  evidence_results?: ContractEvidenceVerification[] | null;
  absence_status?: string | null;
  reasons?: string[] | null;
  [key: string]: unknown;
};

export type ContractClauseResult = {
  clause_id: string;
  v1_clause_id?: string | null;
  v2_clause_id?: string | null;
  status: ClauseComparisonStatus;
  mapping_confidence?: number | null;
  subtree_status?: string | null;
  exact_differences?: ContractExactDifference[];
  risk?: ContractClauseRisk | null;
  explanation?: ContractClauseExplanation | null;
  evidence?: ContractEvidenceRef[];
  citations?: ContractEvidenceRef[];
  verification?: ContractClauseVerification | null;
  v1_text?: string | null;
  v2_text?: string | null;
  finding_id?: string | null;
};

export type ContractComparisonSummary = {
  total_clauses: number;
  unchanged: number;
  modified: number;
  added: number;
  removed: number;
};

export type ContractComparisonStatistics = {
  total_clauses_compared?: number;
  unchanged?: number;
  modified?: number;
  added?: number;
  removed?: number;
  unresolved?: number;
  risk_counts?: Partial<Record<"critical" | "high" | "medium" | "low" | string, number>>;
  llm_calls?: number;
  llm_tokens?: number;
  processing_time_ms?: number;
  verification_rate?: number;
  citation_verification_rate?: number;
};

export type ContractComparisonMetadata = {
  comparison_id?: string | null;
  workspace_id?: string | null;
  document_v1?: ContractDocumentRef | null;
  document_v2?: ContractDocumentRef | null;
  created_at?: string | null;
  status?: string | null;
  quality_status?: string | null;
  quality_reasons?: string[] | null;
  explanation_incomplete?: boolean | null;
};

export type ContractComparisonReport = {
  metadata?: ContractComparisonMetadata | null;
  summary?: ContractComparisonSummary | null;
  statistics?: ContractComparisonStatistics | null;
  clauses?: {
    unchanged?: ContractClauseResult[];
    modified?: ContractClauseResult[];
    added?: ContractClauseResult[];
    removed?: ContractClauseResult[];
    unresolved?: ContractClauseResult[];
  } | null;
  risks?: unknown[];
  citations?: unknown[];
};

export type ComparisonResult = {
  similarities: string[];
  differences: string[];
  contract_comparison?: ContractComparisonReport | null;
};

export type ComparisonReviewStatus =
  | "OPEN"
  | "REVIEWED"
  | "NEEDS_ATTENTION"
  | "ACKNOWLEDGED"
  | string;

export type ComparisonReviewDecision = {
  status: ComparisonReviewStatus;
  reviewer_id?: string | null;
  reviewer_name?: string | null;
  reviewed_at?: string | null;
};

export type ComparisonCommentTarget =
  | "CLAUSE"
  | "FINDING"
  | "EXACT_DIFFERENCE"
  | "EVIDENCE"
  | string;

export type ComparisonComment = {
  id: string;
  clause_id: string;
  target_type: ComparisonCommentTarget;
  target_id?: string | null;
  body: string;
  author_id?: string | null;
  author_name?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type Comparison = {
  id: string;
  workspace_id: string;
  document_ids: string[];
  status: ComparisonStatus;
  result: ComparisonResult | null;
  review?: Record<string, ComparisonReviewDecision> | null;
  comments?: ComparisonComment[] | null;
  created_at: string;
};

export type ComparisonAuditAction =
  | "CLAUSE_OPENED"
  | "REVIEW_STATUS_CHANGED"
  | "COMMENT_ADDED"
  | "COMMENT_EDITED"
  | "COMMENT_DELETED"
  | string;

export type ComparisonAuditEvent = {
  id: string;
  action: ComparisonAuditAction;
  clause_id?: string | null;
  actor_id?: string | null;
  actor_name?: string | null;
  occurred_at: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  target_type?: string | null;
  target_id?: string | null;
  comment_id?: string | null;
};

export type ComparisonAuditTrail = {
  events: ComparisonAuditEvent[];
};

export type ComparisonCreateRequest = {
  document_ids: string[];
  focus?: string | null;
};

export type DocumentMeta = {
  title: string;
  created_at?: string | null;
};
