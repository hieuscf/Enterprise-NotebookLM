import { mapContentOffsetsToDisplay } from "../features/documents/viewer/knowledge/document-structure";

const content = "- Alice manages Project Alpha\n- Bob reviews the design";
const display = "Alice manages Project Alpha\nBob reviews the design";
const needle = "Alice manages Project Alpha";
const start = content.indexOf(needle);
const mapped = mapContentOffsetsToDisplay(
  content,
  display,
  start,
  start + needle.length,
);
if (display.slice(mapped.start, mapped.end) !== needle) {
  console.error("FAIL", mapped, JSON.stringify(display.slice(mapped.start, mapped.end)));
  process.exit(1);
}
console.log("ok - real mapContentOffsetsToDisplay list case");
