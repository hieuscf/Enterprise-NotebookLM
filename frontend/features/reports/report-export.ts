/**
 * =============================================================================
 * File: report-export.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-26 Comparison Report Export.
 * Responsibilities:
 *   - Map export HTTP/code errors to user-facing copy
 *   - Parse Content-Disposition (filename / filename*)
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - exportErrorMessage, filenameFromContentDisposition
 * Database/Table: N/A
 * Related Modules: lib/reports.api, useReportPreview, useReports
 * Important Notes: Delivery UX only. Do not generate files in the browser.
 * =============================================================================
 */

function asString(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value).trim();
  return text ? text : null;
}

export function exportErrorMessage(
  status: number,
  code?: string | null,
  rawMessage?: string | null,
): string {
  const key = String(code ?? "").toLowerCase();
  if (key === "not_ready" || key === "report_not_ready") {
    return "Báo cáo vẫn đang được tạo.";
  }
  if (key === "generation_failed" || key === "report_generation_failed") {
    return "Không xuất được vì quá trình tạo báo cáo đã thất bại.";
  }
  if (
    key === "file_not_found" ||
    key === "file_missing" ||
    key === "file_unavailable" ||
    key === "report_file_not_found"
  ) {
    return "File báo cáo hiện không còn sẵn.";
  }
  if (key === "unsupported_format") {
    return "Định dạng xuất không được hỗ trợ.";
  }
  if (key === "forbidden" || status === 403) {
    return "Bạn không có quyền xuất báo cáo này.";
  }
  if (key === "not_found" || status === 404) {
    return "Không tìm thấy báo cáo.";
  }
  if (status === 409) return "Báo cáo chưa sẵn sàng để xuất.";
  if (status === 0) return "Không kết nối được máy chủ.";
  if (status >= 500) return "Không tải được file báo cáo. Vui lòng thử lại.";
  const text = asString(rawMessage);
  if (text && !/traceback|sqlalchemy|exception|\.py\b/i.test(text)) return text;
  return "Không tải được file báo cáo.";
}

export function filenameFromContentDisposition(
  header: string | null | undefined,
  fallback: string,
): string {
  const value = asString(header);
  if (!value) return fallback;
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(value);
  if (star?.[1]) {
    const encoded = star[1].trim().replace(/^"(.*)"$/, "$1");
    try {
      const decoded = decodeURIComponent(encoded);
      if (decoded && !decoded.includes("/") && !decoded.includes("\\")) {
        return decoded;
      }
    } catch {
      /* keep looking */
    }
  }
  const plain = /filename="([^"]+)"/i.exec(value) ?? /filename=([^;]+)/i.exec(value);
  const name = plain?.[1]?.trim();
  if (name && !name.includes("/") && !name.includes("\\")) return name;
  return fallback;
}
