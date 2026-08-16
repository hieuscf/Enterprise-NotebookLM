/**
 * =============================================================================
 * File: test-report-export-ui.mjs
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Node smoke checks for TASK-CMP-26 export helpers.
 * Responsibilities:
 *   - Mirror report-export.ts error mapping and Content-Disposition parsing
 * Dependencies:
 *   - N/A (self-contained)
 * Public Exports:
 *   - N/A
 * Database/Table: N/A
 * Related Modules: features/reports/report-export.ts
 * Important Notes: Browser must not generate PDF/DOCX. Codes stay user-safe.
 * =============================================================================
 */

function exportErrorMessage(status, code, rawMessage) {
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
  const text = String(rawMessage ?? "").trim();
  if (text && !/traceback|sqlalchemy|exception|\.py\b/i.test(text)) return text;
  return "Không tải được file báo cáo.";
}

function filenameFromContentDisposition(header, fallback) {
  const value = String(header ?? "").trim();
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

function assert(cond, msg) {
  if (!cond) {
    console.error(`FAIL: ${msg}`);
    process.exit(1);
  }
}

assert(exportErrorMessage(409, "not_ready") === "Báo cáo vẫn đang được tạo.", "pending");
assert(
  exportErrorMessage(409, "generation_failed").includes("thất bại"),
  "failed generation",
);
assert(exportErrorMessage(404, "file_not_found").includes("không còn sẵn"), "missing file");
assert(exportErrorMessage(403, "forbidden").includes("quyền"), "access denied");
assert(exportErrorMessage(404, "not_found").includes("Không tìm thấy"), "not found");
assert(exportErrorMessage(0).includes("kết nối"), "network");
assert(
  exportErrorMessage(500, "storage_error", "Traceback (most recent call last)") ===
    "Không tải được file báo cáo. Vui lòng thử lại.",
  "hide traceback",
);

const header =
  'attachment; filename="Hop_dong.pdf"; filename*=UTF-8\'\'H%E1%BB%A3p%20%C4%91%E1%BB%93ng.pdf';
assert(
  filenameFromContentDisposition(header, "fallback.pdf") === "Hợp đồng.pdf",
  "unicode filename*",
);
assert(
  filenameFromContentDisposition('attachment; filename="report.md"', "x") === "report.md",
  "ascii filename",
);
assert(
  filenameFromContentDisposition('attachment; filename="../../secret.pdf"', "safe.pdf") ===
    "safe.pdf",
  "reject traversal filename",
);
assert(filenameFromContentDisposition(null, "report_1") === "report_1", "fallback");

console.log("test-report-export-ui: ok");
