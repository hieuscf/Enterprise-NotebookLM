/**
 * Node-side smoke checks for FR5 location label convention (no Jest yet).
 * Run: node scripts/test-content-location.mjs
 */

function formatContentLocationLabel(location) {
  if (!location) return null;
  if (location.page_number != null) return `Trang ${location.page_number}`;
  if (location.section_index != null) {
    const title = (location.section_title || "").trim();
    return title
      ? `Mục ${location.section_index}: ${title}`
      : `Mục ${location.section_index}`;
  }
  return null;
}

function formatDocumentExtentLabel(fileType, pageCount) {
  if (pageCount == null || pageCount < 0) return null;
  if (fileType === "docx") return pageCount === 1 ? "1 mục" : `${pageCount} mục`;
  if (fileType === "pptx") return pageCount === 1 ? "1 slide" : `${pageCount} slide`;
  if (fileType === "xlsx") return pageCount === 1 ? "1 sheet" : `${pageCount} sheet`;
  return pageCount === 1 ? "1 trang" : `${pageCount} trang`;
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

assert(
  formatContentLocationLabel({ page_number: 3, section_index: null }) === "Trang 3",
  "PDF citation → Trang X",
);
assert(
  formatContentLocationLabel({
    page_number: null,
    section_index: 2,
    section_title: "Phương pháp",
  }) === "Mục 2: Phương pháp",
  "DOCX citation → Mục X: title",
);
assert(
  formatContentLocationLabel({ page_number: null, section_index: 1 }) === "Mục 1",
  "DOCX without title → Mục X",
);
assert(
  formatContentLocationLabel({ page_number: null, section_index: null }) === null,
  "No locator → hide label",
);
assert(formatDocumentExtentLabel("docx", 5) === "5 mục", "DOCX list → X mục");
assert(formatDocumentExtentLabel("pdf", 5) === "5 trang", "PDF list → X trang");
assert(
  !String(formatContentLocationLabel({ section_index: 2 })).includes("Trang"),
  "DOCX label must not contain Trang",
);

if (process.exitCode) {
  process.exit(process.exitCode);
}
console.log("All content-location checks passed.");
