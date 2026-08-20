# =============================================================================
# File: prompts.py
# Module/Service: Summary Service (FR6)
# Layer: Service
# Purpose: Style-specific system/user prompt builders for AI Summary.
# Responsibilities:
#   - Map SummaryStyle → system instructions
#   - Inject allowlisted target_language labels into prompts
#   - Assemble user payload from document chunks / topic hierarchy
# Dependencies:
#   - app.models.enums.SummaryType, TargetLanguage, target_language_label
# Public Exports:
#   - build_summary_prompts, STYLE_SYSTEM_PROMPTS
# Database/Table: N/A
# Related Modules: summary_service
# Important Notes: LLM must return JSON object ``{"summary": "..."}``.
#   Output language comes from TargetLanguage enum labels only (no raw strings).
# =============================================================================

from __future__ import annotations

from app.models.enums import SummaryType, TargetLanguage, target_language_label
from app.repositories.retrieval import ChunkHydrationRow
from app.repositories.summaries import TopicContextRow


def _language_block(language: TargetLanguage) -> str:
    label = target_language_label(language)
    return (
        f"Output language: {label}\n"
        "Requirements:\n"
        "- Generate the summary directly in the requested output language.\n"
        "- Do not translate an already generated summary.\n"
        "- Preserve factual meaning from the provided context.\n"
        "- Do not invent facts.\n"
        "- Preserve names, identifiers, numbers, dates, percentages, "
        "units, formulas and technical terms accurately.\n"
        "- Do not modify citation references "
        "(e.g. [1], [2]) — keep them pointing to the same evidence.\n"
        "- Citation references must continue to point to the original evidence."
    )


def _style_system_prompt(style: SummaryType, language: TargetLanguage) -> str:
    label = target_language_label(language)
    lang_line = (
        f"Write the summary content in {label}. "
        "Keep proper nouns, product names, and citations as in the source when needed."
    )
    if style == SummaryType.short:
        return (
            "You are an enterprise document summarizer. Produce a concise short "
            "summary (3–6 sentences) covering only the main thesis and key facts. "
            f"{lang_line} "
            'Respond with a JSON object: {"summary": "..."}.'
        )
    if style == SummaryType.detailed:
        return (
            "You are an enterprise document summarizer. Produce a detailed summary "
            "that preserves structure, important figures, decisions, and caveats. "
            f"{lang_line} "
            'Respond with a JSON object: {"summary": "..."}.'
        )
    if style == SummaryType.by_topic:
        return (
            "You are an enterprise document summarizer. Organize the summary by "
            "topics/themes. Prefer the provided topic hierarchy when present; "
            "otherwise infer coherent topic sections. "
            f"{lang_line} "
            f"Section titles and content must also be in {label}. "
            "Respond with a JSON object: "
            '{"sections": [{"topic_id": null, "title": "...", "content": "..."}], '
            '"summary": "optional flat markdown for copy"}. '
            "When a provided topic has an id, set topic_id to that UUID string."
        )
    # bullet_points
    return (
        "You are an enterprise document summarizer. Produce a bullet-point "
        "summary (markdown list) of the most important takeaways. "
        f"{lang_line} "
        'Respond with a JSON object: {"summary": "..."}.'
    )


# Kept for tests / introspection — default Vietnamese prompts (style keys only).
STYLE_SYSTEM_PROMPTS: dict[SummaryType, str] = {
    style: _style_system_prompt(style, TargetLanguage.vi) for style in SummaryType
}


def build_summary_prompts(
    *,
    style: SummaryType,
    document_title: str,
    chunks: list[ChunkHydrationRow],
    topics: list[TopicContextRow] | None = None,
    target_language: TargetLanguage = TargetLanguage.vi,
) -> tuple[str, str]:
    """Return (system, user) prompts for one summary LLM call."""
    system = _style_system_prompt(style, target_language)
    body_parts: list[str] = [
        f"Document title: {document_title or '(untitled)'}",
        _language_block(target_language),
    ]

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
