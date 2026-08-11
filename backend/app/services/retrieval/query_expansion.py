# =============================================================================
# File: query_expansion.py
# Module/Service: Search Service / Hybrid Retrieval — Query Expansion
# Layer: Service
# Purpose: Deterministic (0 LLM) query-type detection + lexical expansion for
#   document-level / global questions (RAG answer-quality P1, spec §7-§9).
# Responsibilities:
#   - classify_query_intent(query_text) -> QueryIntent (global | contract | focused)
#   - expand_lexical_query(query_text) -> str for BM25-only lexical widening
# Dependencies:
#   - re, unicodedata only — no embeddings, no LLM, no I/O
# Public Exports:
#   - QueryIntent, classify_query_intent, expand_lexical_query,
#     is_document_level_query, CONTRACT_SECTION_KEYWORDS
# Database/Table: N/A
# Related Modules: hybrid_retrieval_service (BM25 branch), chat/context_assembly
# Important Notes:
#   - Pure functions, deterministic, 0 LLM. Expansion terms are retrieval
#     hints ONLY — they must never be presented to the user as evidence.
#   - Vector query text is left untouched; only BM25 (lexical) query is widened.
# =============================================================================

from __future__ import annotations

import re
import unicodedata
from enum import Enum


_DJ_STROKE_TRANSLATION = str.maketrans({"đ": "d", "Đ": "D"})


def _strip_accents(text: str) -> str:
    # Vietnamese "đ"/"Đ" (U+0111/U+0110) are atomic Unicode code points with
    # no NFD decomposition mapping (unlike "ạ", "ệ", ...), so NFD alone never
    # folds them to "d"/"D" — classification patterns below are written in
    # plain ASCII (e.g. "hop dong", "dieu khoan") and would silently never
    # match any real Vietnamese contract/document phrase without this.
    text = text.translate(_DJ_STROKE_TRANSLATION)
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _fold(text: str) -> str:
    return _strip_accents(text).lower()


class QueryIntent(str, Enum):
    """Deterministic coarse query intent — drives context assembly, not retrieval algorithm."""

    global_overview = "global_overview"
    contract_overview = "contract_overview"
    focused = "focused"


# Vietnamese + English patterns for "tell me about the whole document" style asks.
# Matched against accent-folded, lowercased text (§7).
_GLOBAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bnoi dung chinh\b",
        r"\btom tat\b",
        r"\btai lieu (nay )?(noi|trinh bay|de cap|ve)\b",
        r"\bcac phan chinh\b",
        r"\bmuc dich (cua )?tai lieu\b",
        r"\bphan tich tai lieu\b",
        r"\btong quan (ve )?tai lieu\b",
        r"\bkien truc he thong\b",
        r"\bkien truc (cua )?(he thong|tai lieu)\b",
        r"\b(summary|summarize|overview) (of )?(the )?(document|doc)\b",
        r"\bwhat is (this|the) document about\b",
        r"\bmain (content|points|sections) of (the )?document\b",
    )
)

# Contract/legal overview asks — trigger the contract-structure preference (§9).
_CONTRACT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bhop dong (nay )?(quy dinh|gom|bao gom)\b",
        r"\bnoi dung (chinh )?(cua )?hop dong\b",
        r"\bdieu khoan (chinh )?(cua )?hop dong\b",
        r"\bcac ben (trong|cua) (tai lieu|hop dong)\b",
        r"\bnghia vu (chinh )?cua (cac )?ben\b",
        r"\bquyen (va|loi) (va )?nghia vu\b",
        r"\bthoi han\b.*\bhop dong\b",
        r"\bcham dut hop dong\b",
    )
)

# Deterministic Vietnamese retrieval-hint terms for global/document-level
# questions (§7/§8). These widen BM25 recall only — never presented as facts.
# NOTE: Elasticsearch here uses the default "standard" analyzer (no custom
# accent-folding filter — see app/adapters/elasticsearch_bm25.py), so these
# MUST keep real Vietnamese diacritics to match indexed tokens; accent-folded
# ASCII would never match. Classification above stays accent-folded (robust
# to user input variance); expansion terms below stay properly accented.
GLOBAL_EXPANSION_TERMS: tuple[str, ...] = (
    "mục đích",
    "phạm vi",
    "nội dung",
    "các phần chính",
    "đối tượng",
    "điều khoản",
    "nghĩa vụ",
    "quyền",
    "thời hạn",
    "giới thiệu",
    "tóm tắt",
    "kết luận",
)

# Contract-structure vocabulary (§9) — used ONLY to bias coverage / grouping
# toward sections that actually exist; never used to invent sections.
CONTRACT_SECTION_KEYWORDS: tuple[str, ...] = (
    "các bên",
    "mục đích",
    "phạm vi",
    "định nghĩa",
    "quyền",
    "nghĩa vụ",
    "thanh toán",
    "thời hạn",
    "chấm dứt",
    "bảo mật",
    "trách nhiệm",
    "giải quyết tranh chấp",
    "ký kết",
)


def classify_query_intent(query_text: str) -> QueryIntent:
    """Classify coarse query intent from surface patterns only (0 LLM, 0 embedding)."""
    folded = _fold((query_text or "").strip())
    if not folded:
        return QueryIntent.focused
    for pattern in _CONTRACT_PATTERNS:
        if pattern.search(folded):
            return QueryIntent.contract_overview
    for pattern in _GLOBAL_PATTERNS:
        if pattern.search(folded):
            return QueryIntent.global_overview
    return QueryIntent.focused


def is_document_level_query(query_text: str) -> bool:
    """True for questions that need broad document coverage rather than one fact."""
    return classify_query_intent(query_text) is not QueryIntent.focused


def expand_lexical_query(query_text: str, *, max_extra_terms: int = 6) -> str:
    """Widen a BM25 query with deterministic Vietnamese hint terms (§8).

    Only applied for document-level queries. Terms are appended as additional
    OR-able keywords — the original query text always leads so exact-phrase
    matching in Elasticsearch keeps priority.
    """
    q = (query_text or "").strip()
    if not q:
        return q
    intent = classify_query_intent(q)
    if intent is QueryIntent.focused:
        return q
    extra = list(GLOBAL_EXPANSION_TERMS[:max_extra_terms])
    if intent is QueryIntent.contract_overview:
        extra = list(CONTRACT_SECTION_KEYWORDS[:max_extra_terms])
    return q + " " + " ".join(extra)
