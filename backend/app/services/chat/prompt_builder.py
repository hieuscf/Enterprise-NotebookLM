# =============================================================================
# File: prompt_builder.py
# Module/Service: Chat Service / Prompt Construction (FR4)
# Layer: Service
# Purpose: Pure Prompt Construction — no DB / retrieval I/O.
# Responsibilities:
#   - build_prompt(system, history, retrieval_items, question) → messages payload
#   - Render hierarchical context (document/section/page) instead of bare
#     chunk dumps, and group consecutive chunks under shared headers
#     (RAG answer-quality P1, spec §5-§6)
# Dependencies:
#   - prompt templates module, app.services.retrieval.query_expansion (intent)
# Public Exports:
#   - PromptRetrievalItem, BuiltPrompt, build_prompt,
#     retrieval_candidates_to_prompt_items
# Database/Table: N/A
# Related Modules: answer_generator, context_assembly
# Important Notes:
#   - Caller MUST pass only the latest retrieval_pass items (no merge).
#   - Structured output schema: {answer, citation_ids}.
#   - Never expose raw internal UUIDs as prose — use document_title / a
#     generic label; citation_id brackets are the only id shown to the LLM.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

from app.services.chat.prompt_templates import ANSWER_SYSTEM_PROMPT
from app.services.retrieval.query_expansion import QueryIntent, classify_query_intent


@dataclass(frozen=True, slots=True)
class PromptRetrievalItem:
    """One context chunk for the prompt (already filtered to latest pass)."""

    citation_id: str
    text_snippet: str
    document_id: str | None = None
    rank: int | None = None
    document_title: str | None = None
    section_title: str | None = None
    heading_path: str | None = None
    page_number: int | None = None


@dataclass(frozen=True, slots=True)
class BuiltPrompt:
    """Anthropic-ready prompt parts (pure data)."""

    system: str
    user: str
    citation_id_by_chunk: dict[str, str]


_GLOBAL_SYNTHESIS_HINT = (
    "Lưu ý: Đây là câu hỏi tổng quan về tài liệu. Hãy tổng hợp (synthesize) thông tin "
    "từ NHIỀU đoạn trích bên trên — không chỉ dựa vào một đoạn duy nhất — và trình bày "
    "thành các ý chính có đánh số khi phù hợp."
)
_CONTRACT_SYNTHESIS_HINT = (
    "Lưu ý: Đây là câu hỏi về nội dung hợp đồng/pháp lý. Hãy tổng hợp các điều khoản "
    "liên quan có trong ngữ cảnh (các bên, phạm vi, quyền, nghĩa vụ, thời hạn, chấm dứt...) "
    "— chỉ nêu những phần THỰC SỰ có trong ngữ cảnh, không suy đoán các mục còn thiếu."
)


def _section_label(item: PromptRetrievalItem) -> str | None:
    return item.heading_path or item.section_title or None


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
        retrieval_items: Context from **latest retrieval_pass only**, already
            ordered/grouped by context assembly (document -> section -> order).
        question: Current user question (may be rewritten).
    """
    system = (system_prompt or ANSWER_SYSTEM_PROMPT).strip()
    citation_map: dict[str, str] = {}
    context_blocks: list[str] = []

    last_doc_label: str | None = None
    last_section_label: str | None = None
    for item in retrieval_items:
        cid = str(item.citation_id).strip()
        if not cid:
            continue
        citation_map[cid] = cid

        # Never expose raw document_id UUIDs as prose (§5) — fall back to a
        # generic label instead of the internal id when no title is known.
        doc_label = item.document_title or "tài liệu"
        section_label = _section_label(item)

        header_lines: list[str] = []
        if doc_label != last_doc_label:
            header_lines.append(f"[Tài liệu] {doc_label}")
            last_doc_label = doc_label
            last_section_label = None  # force section header to repeat after a doc change
        if section_label and section_label != last_section_label:
            header_lines.append(f"[Phần] {section_label}")
            last_section_label = section_label

        page_prefix = f"(Trang {item.page_number}) " if item.page_number is not None else ""
        block_lines = list(header_lines)
        block_lines.append(f"[{cid}] {page_prefix}{item.text_snippet.strip()}")
        context_blocks.append("\n".join(block_lines))

    history_lines: list[str] = []
    for turn in history or []:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        history_lines.append(f"{role.upper()}: {content}")

    query_type = classify_query_intent(question)

    parts: list[str] = []
    if history_lines:
        parts.append("Conversation history:\n" + "\n".join(history_lines))
    if context_blocks:
        parts.append(
            "Retrieved context — grouped by document/section, in this order "
            "(use only these citation_ids, shown in [brackets]):\n"
            + "\n\n".join(context_blocks)
        )
    else:
        parts.append("Retrieved context: (none)")
    parts.append(f"Question:\n{question.strip()}")
    if query_type is QueryIntent.global_overview:
        parts.append(_GLOBAL_SYNTHESIS_HINT)
    elif query_type is QueryIntent.contract_overview:
        parts.append(_CONTRACT_SYNTHESIS_HINT)
    parts.append(
        "Respond with a single JSON object: "
        '{"answer": "<markdown answer>", "citation_ids": ["<id>", ...]}'
    )
    return BuiltPrompt(system=system, user="\n\n".join(parts), citation_id_by_chunk=citation_map)


def retrieval_candidates_to_prompt_items(
    items: Sequence[Any],
) -> list[PromptRetrievalItem]:
    """Map in-memory RetrievalCandidate list → PromptRetrievalItem (citation_id=chunk_id).

    Carries hierarchical metadata (document_title/section_title/heading_path/
    page_number) through when present so ``build_prompt`` can render grouped,
    structure-aware context instead of bare chunk dumps (spec §5-§6).
    """
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
                document_title=getattr(item, "document_title", None) or None,
                section_title=getattr(item, "section_title", None) or None,
                heading_path=getattr(item, "heading_path", None) or None,
                page_number=getattr(item, "page_number", None),
            )
        )
    return out
