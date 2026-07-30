/**
 * =============================================================================
 * File: upload-constraints.ts
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Client-side upload constraints + validation for document upload (FR2).
 * Responsibilities:
 *   - Define allowed extensions, max file size, max concurrent uploads
 *   - Validate a File before it is queued for upload
 * Dependencies:
 *   - None
 * Public Exports:
 *   - ALLOWED_EXTENSIONS, ACCEPT_ATTRIBUTE, MAX_FILE_SIZE_BYTES,
 *     MAX_CONCURRENT_UPLOADS, validateFile, formatBytes
 * Database/Table: N/A
 * Related Modules: app/services/documents.py (ALLOWED_EXTENSIONS — keep in sync)
 * Important Notes: Backend does not enforce a max size itself (only extension +
 *   empty-file checks) — this limit is a client-side UX guard only. A reverse
 *   proxy may still reject larger payloads with 413, handled separately.
 * =============================================================================
 */

/** Kept in sync with backend `ALLOWED_EXTENSIONS` in app/services/documents.py. */
export const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".pptx", ".txt"] as const;

export const ACCEPT_ATTRIBUTE = ALLOWED_EXTENSIONS.join(",");

/** Default 50MB — easy to bump if backend/proxy limits change. */
export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

/** Max number of upload requests in flight at once; extra files stay "queued". */
export const MAX_CONCURRENT_UPLOADS = 3;

export type FileValidationError = "unsupported_type" | "too_large" | "empty_file";

export const FILE_VALIDATION_MESSAGE: Record<FileValidationError, string> = {
  unsupported_type: `Chỉ hỗ trợ định dạng ${ALLOWED_EXTENSIONS.join(", ")}.`,
  too_large: `Kích thước file vượt quá ${formatBytesStatic(MAX_FILE_SIZE_BYTES)}.`,
  empty_file: "File trống, vui lòng chọn file khác.",
};

function formatBytesStatic(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)}MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${bytes}B`;
}

export function formatBytes(bytes: number): string {
  return formatBytesStatic(bytes);
}

function hasAllowedExtension(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** Returns null when the file passes all client-side checks. */
export function validateFile(file: File): FileValidationError | null {
  if (!hasAllowedExtension(file.name)) return "unsupported_type";
  if (file.size === 0) return "empty_file";
  if (file.size > MAX_FILE_SIZE_BYTES) return "too_large";
  return null;
}

/** Default title suggestion: filename without its extension. */
export function titleFromFilename(filename: string): string {
  const idx = filename.lastIndexOf(".");
  return idx > 0 ? filename.slice(0, idx) : filename;
}
