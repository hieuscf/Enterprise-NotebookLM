/**
 * =============================================================================
 * File: summaries.ts
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Summaries API matching OpenAPI (FR6).
 * Responsibilities:
 *   - Align Summary / SummaryStyle / SummaryStatus with backend SummaryResponse
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml Summary schema
 * Public Exports:
 *   - SummaryStyle, SummaryStatus, TargetLanguage, SummaryTopicSection, Summary,
 *     SummaryCreateRequest
 * Database/Table: summaries
 * Related Modules: lib/summaries.api, features/summaries/*
 * Important Notes: source_version_id is public (FE current-vs-old UX).
 *   sections is set for by_topic only. target_language defaults to vi.
 * =============================================================================
 */

export type SummaryStyle = "short" | "detailed" | "by_topic" | "bullet_points";

export type SummaryStatus = "processing" | "completed" | "failed";

export type TargetLanguage = "vi" | "en";

export type SummaryTopicSection = {
  topic_id: string | null;
  title: string;
  content: string;
};

export type Summary = {
  id: string;
  document_id: string;
  source_version_id: string;
  style: SummaryStyle;
  target_language: TargetLanguage;
  status: SummaryStatus;
  content: string | null;
  sections: SummaryTopicSection[] | null;
  created_at: string;
};

export type SummaryCreateRequest = {
  style: SummaryStyle;
  target_language?: TargetLanguage;
};
