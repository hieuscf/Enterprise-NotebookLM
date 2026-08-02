/**
 * =============================================================================
 * File: search-score.ts
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Client-side score gate aligned with backend search_min_score (FR3).
 * Responsibilities:
 *   - Filter SearchResultItem list to score >= threshold; re-rank for display
 * Dependencies:
 *   - types/search
 * Public Exports:
 *   - SEARCH_MIN_DISPLAY_SCORE, filterResultsByMinScore
 * Database/Table: N/A
 * Related Modules: hooks/useSearch.ts, features/search/SearchResults.tsx
 * Important Notes: Must match backend Settings.search_min_score default (0.6).
 * =============================================================================
 */

import type { SearchResultItem } from "@/types/search";

/** Default minimum score shown in Search UI (backend: SEARCH_MIN_SCORE / 0.6). */
export const SEARCH_MIN_DISPLAY_SCORE = 0.6;

/**
 * Keep only hits with score >= minScore and renumber rank for display.
 */
export function filterResultsByMinScore(
  results: SearchResultItem[],
  minScore: number = SEARCH_MIN_DISPLAY_SCORE,
): SearchResultItem[] {
  return results
    .filter((item) => Number(item.score) >= minScore)
    .map((item, index) => ({ ...item, rank: index + 1 }));
}
