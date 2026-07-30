/**
 * =============================================================================
 * File: pipeline-stages.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Single source of truth for the 6-step v3 pipeline order, Vietnamese
 *          labels, and icons shown in PipelineStatusTracker (FR2 / FR13).
 * Responsibilities:
 *   - Define PIPELINE_STAGE_ORDER (document_understanding → indexing)
 *   - Map stage → user-facing Vietnamese label (separate from stage → icon)
 *   - Map pipeline stage status → icon/label/animation for the stepper UI
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - PIPELINE_STAGE_ORDER, STAGE_LABEL_VI, STAGE_ICON
 *   - STATUS_LABEL_VI, STATUS_ICON, isTerminalPipelineStatus
 * Database/Table: pipeline_stage_logs.stage (enum v3)
 * Related Modules: features/documents/PipelineStatusTracker, types/documents
 * Important Notes: Edit STAGE_LABEL_VI / STAGE_ICON here only — never inline
 *   the mapping in a component, so copy/icon changes stay one-line edits.
 * =============================================================================
 */

import {
  Boxes,
  CheckCircle2,
  Circle,
  ListChecks,
  ListTree,
  Loader2,
  type LucideIcon,
  Network,
  ScanSearch,
  Sparkles,
  XCircle,
} from "lucide-react";

import type { PipelineStageNameV3, PipelineStatus } from "@/types/documents";

/** Fixed v3 order — never derive this from API data (stage order is a contract). */
export const PIPELINE_STAGE_ORDER: readonly PipelineStageNameV3[] = [
  "document_understanding",
  "cleaning_normalize",
  "hierarchical_chunking",
  "embedding",
  "graph_extraction",
  "indexing",
];

/** User-facing Vietnamese copy — describes the action, not the technical stage name. */
export const STAGE_LABEL_VI: Record<PipelineStageNameV3, string> = {
  document_understanding: "Trích xuất bố cục tài liệu",
  cleaning_normalize: "Làm sạch & chuẩn hoá nội dung",
  hierarchical_chunking: "Phân đoạn theo cấu trúc",
  embedding: "Tạo vector nhúng",
  graph_extraction: "Trích xuất tri thức liên kết",
  indexing: "Lập chỉ mục tìm kiếm",
};

/** Icon per stage — kept separate from the label so either can change independently. */
export const STAGE_ICON: Record<PipelineStageNameV3, LucideIcon> = {
  document_understanding: ScanSearch,
  cleaning_normalize: Sparkles,
  hierarchical_chunking: ListTree,
  embedding: Boxes,
  graph_extraction: Network,
  indexing: ListChecks,
};

export const STATUS_LABEL_VI: Record<PipelineStatus, string> = {
  pending: "Chưa tới",
  running: "Đang xử lý",
  completed: "Hoàn tất",
  failed: "Lỗi",
};

/** Icon shown per-step based on that step's current status (overrides the stage icon). */
export const STATUS_ICON: Record<PipelineStatus, LucideIcon> = {
  pending: Circle,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
};

export function isTerminalPipelineStatus(status: PipelineStatus): boolean {
  return status === "completed" || status === "failed";
}
