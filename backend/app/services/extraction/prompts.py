# =============================================================================
# File: prompts.py
# Module/Service: Extraction Service (FR7)
# Layer: Service
# Purpose: Per-type system/user prompt templates for structured LLM extraction.
# Responsibilities:
#   - Build table / figures / timeline / LLM-entity prompts from version chunks
#   - Inject allowlisted target_language for descriptive text fields only
# Dependencies:
#   - ChunkHydrationRow, TargetLanguage, target_language_label
# Public Exports:
#   - build_table_prompts, build_figures_prompts, build_timeline_prompts,
#     build_llm_entity_prompts
# Database/Table: N/A
# Related Modules: extraction_service
# Important Notes: One prompt family per extraction_type — no universal prompt.
#   Field names stay English; only narrative text follows target_language.
# =============================================================================

from __future__ import annotations

from app.models.enums import TargetLanguage, target_language_label
from app.repositories.retrieval import ChunkHydrationRow


def _format_chunks(chunks: list[ChunkHydrationRow]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        header = f"[chunk_id={chunk.chunk_id} index={chunk.chunk_index}]"
        if chunk.heading_path:
            header += f" heading={chunk.heading_path}"
        parts.append(f"{header}\n{(chunk.content or '').strip()}")
    return "\n\n".join(parts)


def _language_rules(language: TargetLanguage) -> str:
    label = target_language_label(language)
    return (
        f"Output language for descriptive text fields: {label}.\n"
        "Rules for language:\n"
        "- Generate descriptive / narrative text directly in the requested output language.\n"
        "- Do not translate an already generated extraction.\n"
        "- Preserve numbers, dates, identifiers, codes, units, and proper nouns exactly.\n"
        "- Do not translate JSON field names (headers keys, schema keys stay English).\n"
        "- Do not invent facts absent from the chunks."
    )


def build_table_prompts(
    *,
    document_title: str,
    chunks: list[ChunkHydrationRow],
    target_language: TargetLanguage = TargetLanguage.vi,
) -> tuple[str, str]:
    system = (
        "You extract tabular data from document chunks for an enterprise knowledge system.\n"
        "Return ONLY a JSON object with keys:\n"
        '  "headers": string[] — column names in display order\n'
        '  "rows": object[] — each object maps every header to a cell value\n'
        "Rules:\n"
        "- Preserve column names from the source when present.\n"
        "- Do not invent values that are not supported by the chunks.\n"
        "- If no table is present, return headers for an empty table and rows=[].\n"
        "- Do not wrap the JSON in Markdown.\n"
        f"{_language_rules(target_language)}"
    )
    user = (
        f"Document title: {document_title}\n\n"
        f"Chunks:\n{_format_chunks(chunks)}\n\n"
        "Extract all tabular data into the required JSON schema."
    )
    return system, user


def build_figures_prompts(
    *,
    document_title: str,
    chunks: list[ChunkHydrationRow],
    target_language: TargetLanguage = TargetLanguage.vi,
) -> tuple[str, str]:
    system = (
        "You extract quantitative figures/metrics from document chunks.\n"
        "Return ONLY a JSON object with key:\n"
        '  "figures": array of { "metric": string, "value": number|string, '
        '"unit": string|null, "context": string|null }\n'
        "Rules:\n"
        "- Capture metric name, numeric/string value, unit, and short context.\n"
        "- Do not invent metrics absent from the chunks.\n"
        "- Do not wrap the JSON in Markdown.\n"
        f"{_language_rules(target_language)}"
    )
    user = (
        f"Document title: {document_title}\n\n"
        f"Chunks:\n{_format_chunks(chunks)}\n\n"
        "Extract figures/metrics into the required JSON schema."
    )
    return system, user


def build_timeline_prompts(
    *,
    document_title: str,
    chunks: list[ChunkHydrationRow],
    target_language: TargetLanguage = TargetLanguage.vi,
) -> tuple[str, str]:
    system = (
        "You extract chronological events from document chunks.\n"
        "Return ONLY a JSON object with key:\n"
        '  "events": array of { "date_or_period": string, "event": string, '
        '"source_chunk_id": uuid-string }\n'
        "Rules:\n"
        "- source_chunk_id MUST be one of the chunk_id values provided.\n"
        "- Prefer exact dates when stated; otherwise keep periods "
        '(e.g. "Q1 2024", "2025–2026").\n'
        "- Do not fabricate exact dates when the source only gives a period.\n"
        "- Do not invent events absent from the chunks.\n"
        "- Do not wrap the JSON in Markdown.\n"
        f"{_language_rules(target_language)}"
    )
    user = (
        f"Document title: {document_title}\n\n"
        f"Chunks:\n{_format_chunks(chunks)}\n\n"
        "Extract timeline events into the required JSON schema."
    )
    return system, user


def build_llm_entity_prompts(
    *,
    document_title: str,
    chunks: list[ChunkHydrationRow],
    target_language: TargetLanguage = TargetLanguage.vi,
) -> tuple[str, str]:
    """LLM_ENTITY_EXTRACTION fallback — not used for standard Graph entity reuse."""
    system = (
        "You extract named entities that the existing graph entity model cannot represent.\n"
        "Return ONLY a JSON object with key:\n"
        '  "entities": array of { "name": string, "type": string, '
        '"description": string|null }\n'
        "Rules:\n"
        "- Use precise entity types and attributes grounded in the chunks.\n"
        "- Do not invent entities.\n"
        "- Do not wrap the JSON in Markdown.\n"
        f"{_language_rules(target_language)}"
    )
    user = (
        f"Document title: {document_title}\n\n"
        f"Chunks:\n{_format_chunks(chunks)}\n\n"
        "Extract entities into the required JSON schema."
    )
    return system, user
