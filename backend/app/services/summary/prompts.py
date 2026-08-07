# =============================================================================
# File: prompts.py
# Module/Service: Summary Service (FR6)
# Layer: Service
# Purpose: Style-specific system/user prompt builders for AI Summary.
# Responsibilities:
#   - Map SummaryStyle → system instructions
#   - Assemble user payload from document chunks / topic hierarchy
# Dependencies:
#   - app.models.enums.SummaryType
# Public Exports:
#   - build_summary_prompts, STYLE_SYSTEM_PROMPTS
# Database/Table: N/A
# Related Modules: summary_service
# Important Notes: LLM must return JSON object ``{"summary": "..."}``.
# =============================================================================

from __future__ import annotations

from app.models.enums import SummaryType
from app.repositories.retrieval import ChunkHydrationRow
from app.repositories.summaries import TopicContextRow

STYLE_SYSTEM_PROMPTS: dict[SummaryType, str] = {
    SummaryType.short: (
        "You are an enterprise document summarizer. Produce a concise short "
        "summary (3–6 sentences) covering only the main thesis and key facts. "
        "Respond with a JSON object: {\"summary\": \"...\"}."
    ),
    SummaryType.detailed: (
        "You are an enterprise document summarizer. Produce a detailed summary "
        "that preserves structure, important figures, decisions, and caveats. "
        "Respond with a JSON object: {\"summary\": \"...\"}."
    ),
    SummaryType.by_topic: (
        "You are an enterprise document summarizer. Organize the summary by "
        "topics/themes. Prefer the provided topic hierarchy when present; "
        "otherwise infer coherent topic sections. "
        "Respond with a JSON object: "
        "{\"sections\": [{\"topic_id\": null, \"title\": \"...\", \"content\": \"...\"}], "
        "\"summary\": \"optional flat markdown for copy\"}. "
        "When a provided topic has an id, set topic_id to that UUID string."
    ),
    SummaryType.bullet_points: (
        "You are an enterprise document summarizer. Produce a bullet-point "
        "summary (markdown list) of the most important takeaways. "
        "Respond with a JSON object: {\"summary\": \"...\"}."
    ),
}


def build_summary_prompts(
    *,
    style: SummaryType,
    document_title: str,
    chunks: list[ChunkHydrationRow],
    topics: list[TopicContextRow] | None = None,
) -> tuple[str, str]:
    """Return (system, user) prompts for one summary LLM call."""
    system = STYLE_SYSTEM_PROMPTS[style]
    body_parts: list[str] = [f"Document title: {document_title or '(untitled)'}"]

    if style == SummaryType.by_topic and topics:
        body_parts.append("Topic hierarchy (from knowledge graph):")
        for topic in topics:
            indent = "  " * max(0, int(topic.level))
            snippet = (topic.summary or "").strip()
            if snippet:
                body_parts.append(f"{indent}- id={topic.topic_id} | {topic.name}: {snippet}")
            else:
                body_parts.append(f"{indent}- id={topic.topic_id} | {topic.name}")
        body_parts.append("Supporting document excerpts:")
    else:
        body_parts.append("Document excerpts (current version only):")

    for chunk in chunks:
        loc_bits: list[str] = []
        if chunk.heading_path:
            loc_bits.append(chunk.heading_path)
        elif chunk.section:
            loc_bits.append(chunk.section)
        if chunk.page_number is not None:
            loc_bits.append(f"p.{chunk.page_number}")
        if chunk.section_index is not None:
            loc_bits.append(f"sec.{chunk.section_index}")
        loc = f" [{', '.join(loc_bits)}]" if loc_bits else ""
        body_parts.append(f"--- chunk{loc} ---\n{(chunk.content or '').strip()}")

    user = "\n\n".join(body_parts)
    return system, user
