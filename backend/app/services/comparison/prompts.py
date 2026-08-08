# =============================================================================
# File: prompts.py
# Module/Service: Comparison Service (FR8)
# Layer: Service
# Purpose: System/user prompt builders for multi-document comparison (UC7).
# Responsibilities:
#   - Assemble per-document summary or chunk context into one LLM prompt
#   - Optionally constrain comparison to a focus topic
# Dependencies:
#   - ChunkHydrationRow
# Public Exports:
#   - DocumentCompareContext, build_comparison_prompts
# Database/Table: N/A
# Related Modules: comparison_service, result_schemas
# Important Notes:
#   - Exactly one LLM call; output must be similarities/differences JSON only.
#   - Prompt forbids inventing facts outside provided context.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field

from app.repositories.retrieval import ChunkHydrationRow

COMPARISON_SYSTEM_PROMPT = (
    "You are an enterprise multi-document analyst. Compare the provided documents "
    "using ONLY the given context (summaries and/or excerpts).\n"
    "Return ONLY a JSON object with keys:\n"
    '  "similarities": string[] — points that are supported as shared across documents\n'
    '  "differences": string[] — points that are supported as differing between documents\n'
    "Rules:\n"
    "- Do not invent facts, figures, or claims that are not supported by the context.\n"
    "- If the context is insufficient to compare an aspect, omit that aspect entirely "
    "(do not guess or speculate).\n"
    "- Prefer concrete, concise bullet-like statements.\n"
    "- Do not wrap the JSON in Markdown."
)


@dataclass(frozen=True, slots=True)
class DocumentCompareContext:
    """Per-document payload fed into the comparison prompt."""

    document_id: str
    title: str
    source: str  # "summary" | "chunks"
    summary_text: str | None = None
    chunks: list[ChunkHydrationRow] = field(default_factory=list)


def build_comparison_prompts(
    *,
    documents: list[DocumentCompareContext],
    focus: str | None = None,
) -> tuple[str, str]:
    """Return (system, user) prompts for one comparison LLM call."""
    focus_term = (focus or "").strip()
    system = COMPARISON_SYSTEM_PROMPT
    if focus_term:
        system += (
            f'\nFocus constraint: Limit the comparison to the topic "{focus_term}". '
            "Ignore aspects outside this focus unless needed to state a focused "
            "similarity or difference. If the context lacks enough focused evidence, "
            "return empty arrays rather than inventing content."
        )

    parts: list[str] = [
        f"Compare the following {len(documents)} documents.",
    ]
    if focus_term:
        parts.append(f"Comparison focus: {focus_term}")

    for index, doc in enumerate(documents, start=1):
        title = (doc.title or "").strip() or "(untitled)"
        header = f"=== Document {index}: {title} (id={doc.document_id}) ==="
        if doc.source == "summary" and (doc.summary_text or "").strip():
            parts.append(f"{header}\nSource: completed summary\n{(doc.summary_text or '').strip()}")
            continue

        chunk_blocks: list[str] = []
        for chunk in doc.chunks:
            loc_bits: list[str] = []
            if chunk.heading_path:
                loc_bits.append(chunk.heading_path)
            elif chunk.section:
                loc_bits.append(chunk.section)
            if chunk.page_number is not None:
                loc_bits.append(f"p.{chunk.page_number}")
            if chunk.chunk_index is not None:
                loc_bits.append(f"chunk.{chunk.chunk_index}")
            loc = f" [{', '.join(loc_bits)}]" if loc_bits else ""
            chunk_blocks.append(f"--- excerpt{loc} ---\n{(chunk.content or '').strip()}")
        body = "\n\n".join(chunk_blocks) if chunk_blocks else "(no excerpts available)"
        parts.append(f"{header}\nSource: topic-ranked excerpts\n{body}")

    parts.append(
        "Produce the similarities/differences JSON object now. "
        "Omit any aspect not supported by the provided context."
    )
    return system, "\n\n".join(parts)
