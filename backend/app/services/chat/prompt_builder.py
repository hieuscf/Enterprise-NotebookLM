# =============================================================================
# File: prompt_builder.py
# Module/Service: Chat Service / Prompt Construction (FR4)
# Layer: Service
# Purpose: Pure Prompt Construction — no DB / retrieval I/O.
# Responsibilities:
#   - build_prompt(system, history, retrieval_items, question) → messages payload
# Dependencies:
#   - prompt templates module
# Public Exports:
#   - PromptRetrievalItem, BuiltPrompt, build_prompt
# Database/Table: N/A
# Related Modules: answer_generator
# Important Notes:
#   - Caller MUST pass only the latest retrieval_pass items (no merge).
#   - Structured output schema: {answer, citation_ids}.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

from app.services.chat.prompt_templates import ANSWER_SYSTEM_PROMPT


@dataclass(frozen=True, slots=True)
class PromptRetrievalItem:
    """One context chunk for the prompt (already filtered to latest pass)."""

    citation_id: str
    text_snippet: str
    document_id: str | None = None
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class BuiltPrompt:
    """Anthropic-ready prompt parts (pure data)."""

    system: str
    user: str
    citation_id_by_chunk: dict[str, str]


def build_prompt(
    system_prompt: str,
    history: Sequence[dict[str, str]] | None,
    retrieval_items: Sequence[PromptRetrievalItem],
    question: str,
) -> BuiltPrompt:
    """Build system + user prompt for the single answer LLM call.

    Args:
        system_prompt: Base system instructions (from templates/config).
        history: Prior turns ``{"role": "user"|"assistant", "content": "..."}``.
        retrieval_items: Context from **latest retrieval_pass only**.
        question: Current user question (may be rewritten).
    """
    system = (system_prompt or ANSWER_SYSTEM_PROMPT).strip()
    citation_map: dict[str, str] = {}
    context_blocks: list[str] = []
    for item in retrieval_items:
        cid = str(item.citation_id).strip()
        if not cid:
            continue
        citation_map[cid] = cid
        rank_label = f"rank={item.rank}" if item.rank is not None else "rank=?"
        doc_label = item.document_id or "unknown"
        context_blocks.append(
            f"[{cid}] ({rank_label}, document_id={doc_label})\n{item.text_snippet.strip()}"
        )

    history_lines: list[str] = []
    for turn in history or []:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        history_lines.append(f"{role.upper()}: {content}")

    parts: list[str] = []
    if history_lines:
        parts.append("Conversation history:\n" + "\n".join(history_lines))
    if context_blocks:
        parts.append(
            "Retrieved context (use only these citation_ids):\n"
            + "\n\n".join(context_blocks)
        )
    else:
        parts.append("Retrieved context: (none)")
    parts.append(f"Question:\n{question.strip()}")
    parts.append(
        "Respond with a single JSON object: "
        '{"answer": "<markdown answer>", "citation_ids": ["<id>", ...]}'
    )
    return BuiltPrompt(system=system, user="\n\n".join(parts), citation_id_by_chunk=citation_map)


def retrieval_candidates_to_prompt_items(
    items: Sequence[Any],
) -> list[PromptRetrievalItem]:
    """Map in-memory RetrievalCandidate list → PromptRetrievalItem (citation_id=chunk_id)."""
    out: list[PromptRetrievalItem] = []
    for item in items:
        chunk_id = getattr(item, "chunk_id", None)
        if chunk_id is None:
            continue
        cid = str(chunk_id if isinstance(chunk_id, UUID) else chunk_id)
        doc = getattr(item, "document_id", None)
        out.append(
            PromptRetrievalItem(
                citation_id=cid,
                text_snippet=str(getattr(item, "text_snippet", "") or ""),
                document_id=str(doc) if doc else None,
                rank=getattr(item, "rank", None),
            )
        )
    return out
