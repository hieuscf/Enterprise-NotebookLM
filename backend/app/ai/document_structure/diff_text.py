# =============================================================================
# File: diff_text.py
# Module/Service: Clause Diff Engine (FR8 / TASK-CMP-04)
# Layer: Service
# Purpose: Deterministic content equality and token/sentence edit extraction.
# Responsibilities:
#   - Compare CMP-02 normalized/folded bodies (whitespace already collapsed)
#   - SHA-256 fingerprint for unchanged short-circuit
#   - Word-level SequenceMatcher + optional sentence-level SequenceMatcher
# Dependencies:
#   - stdlib hashlib / difflib / re
#   - mapping_similarity token class; hierarchical_chunking.sentence_splitter
# Public Exports:
#   - content_fingerprint, select_comparison_text, derived_comparison_text,
#     content_texts, texts_equal, token_changes, sentence_changes
# Database/Table: N/A
# Related Modules: diff_engine; CMP-06 consumes TextChange lists
# Important Notes:
#   - 0 LLM. Does not paraphrase, stem, or rewrite originals.
#   - Derived comparison text only — NormalizedUnit fields are never written.
# =============================================================================

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from app.ai.document_structure.diff_config import DiffConfig
from app.ai.document_structure.diff_types import ChangeType, TextChange
from app.ai.document_structure.normalization import NormalizedUnit, normalize_body
from app.ai.document_structure.patterns import fold_ocr_text
from app.ai.hierarchical_chunking.sentence_splitter import split_sentences

# Same Unicode token class as mapping_similarity / retrieval reranker heuristic.
_TOKEN_RE = re.compile(
    r"[a-z0-9àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+",
    re.I,
)


def content_fingerprint(text: str) -> str:
    """Deterministic hex digest of comparison text. Not a legal identity."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def select_comparison_text(unit: NormalizedUnit | None) -> tuple[str, str]:
    """Prefer folded_body (OCR/whitespace-safe); fall back to normalized_body.

    Returns ``(text, field_name)``. Empty exclusive spans (article headings)
    yield empty text — that is not “missing from retrieval”.
    """
    if unit is None:
        return "", "folded_body"
    folded = (unit.folded_body or "").strip()
    if folded:
        return folded, "folded_body"
    normalized = (unit.normalized_body or "").strip()
    if normalized:
        return normalized, "normalized_body"
    return "", "folded_body"


def derived_comparison_text(unit: NormalizedUnit | None) -> str:
    """Whitespace-collapsed original span without heading-line strip.

    CMP-02 may treat a wrapped first line as ``original_heading`` and drop it
    from ``normalized_body``. This derived form keeps the exclusive span so
    PDF line-wrap alone is not MODIFIED. Originals are never written.
    """
    if unit is None:
        return ""
    body = normalize_body(unit.original_text, heading=None)
    return fold_ocr_text(body).strip()


def content_texts(
    source: NormalizedUnit | None,
    target: NormalizedUnit | None,
) -> tuple[bool, str, str, str]:
    """Return ``(changed, field, left, right)`` for deterministic comparison."""
    source_primary, field = select_comparison_text(source)
    target_primary, _ = select_comparison_text(target)
    if texts_equal(source_primary, target_primary):
        return False, field, source_primary, target_primary
    source_derived = derived_comparison_text(source)
    target_derived = derived_comparison_text(target)
    if source_derived or target_derived:
        if texts_equal(source_derived, target_derived):
            return False, "derived_original", source_derived, target_derived
        return True, "derived_original", source_derived, target_derived
    return True, field, source_primary, target_primary


def texts_equal(left: str, right: str) -> bool:
    return (left or "") == (right or "")


def token_list(text: str) -> list[str]:
    return _TOKEN_RE.findall(text or "")


def token_changes(
    old_text: str,
    new_text: str,
    *,
    config: DiffConfig | None = None,
) -> list[TextChange]:
    """Word-level insert/delete/replace (optional moved-span rewrite)."""
    cfg = config or DiffConfig()
    old_tokens = token_list(old_text)
    new_tokens = token_list(new_text)
    if old_tokens == new_tokens:
        return []
    matcher = SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    raw: list[TextChange] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = _join_tokens(old_tokens[i1:i2], cfg.max_change_snippet_tokens)
        new = _join_tokens(new_tokens[j1:j2], cfg.max_change_snippet_tokens)
        if tag == "insert":
            change_type = ChangeType.INSERTED
        elif tag == "delete":
            change_type = ChangeType.DELETED
        else:
            change_type = ChangeType.REPLACED
        raw.append(
            TextChange(
                change_type=change_type,
                old=old,
                new=new,
                level="token",
                old_index=i1,
                new_index=j1,
            )
        )
    if cfg.detect_moved_spans:
        return _mark_moved(raw)
    return raw


def sentence_changes(
    old_text: str,
    new_text: str,
    *,
    config: DiffConfig | None = None,
) -> list[TextChange]:
    """Sentence-level insert/delete/replace using the existing splitter."""
    cfg = config or DiffConfig()
    old_sents = split_sentences(old_text or "")
    new_sents = split_sentences(new_text or "")
    if old_sents == new_sents:
        return []
    if len(old_sents) <= 1 and len(new_sents) <= 1:
        return []
    matcher = SequenceMatcher(None, old_sents, new_sents, autojunk=False)
    raw: list[TextChange] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = " ".join(old_sents[i1:i2])
        new = " ".join(new_sents[j1:j2])
        if tag == "insert":
            change_type = ChangeType.INSERTED
        elif tag == "delete":
            change_type = ChangeType.DELETED
        else:
            change_type = ChangeType.REPLACED
        raw.append(
            TextChange(
                change_type=change_type,
                old=old,
                new=new,
                level="sentence",
                old_index=i1,
                new_index=j1,
            )
        )
    if cfg.detect_moved_spans:
        return _mark_moved(raw)
    return raw


def _join_tokens(tokens: list[str], limit: int) -> str:
    if len(tokens) <= limit:
        return " ".join(tokens)
    head = " ".join(tokens[: limit // 2])
    tail = " ".join(tokens[-(limit // 2) :])
    return f"{head} … {tail}"


def _mark_moved(changes: list[TextChange]) -> list[TextChange]:
    """Rewrite exact deleted↔inserted span pairs as MOVED (still deterministic)."""
    deleted = [
        (index, item)
        for index, item in enumerate(changes)
        if item.change_type is ChangeType.DELETED and item.old
    ]
    inserted = [
        (index, item)
        for index, item in enumerate(changes)
        if item.change_type is ChangeType.INSERTED and item.new
    ]
    used_del: set[int] = set()
    used_ins: set[int] = set()
    rewritten = list(changes)
    for d_idx, deleted_item in deleted:
        for i_idx, inserted_item in inserted:
            if i_idx in used_ins:
                continue
            if deleted_item.old == inserted_item.new:
                used_del.add(d_idx)
                used_ins.add(i_idx)
                rewritten[d_idx] = TextChange(
                    change_type=ChangeType.MOVED,
                    old=deleted_item.old,
                    new=deleted_item.old,
                    level=deleted_item.level,
                    old_index=deleted_item.old_index,
                    new_index=inserted_item.new_index,
                )
                rewritten[i_idx] = TextChange(
                    change_type=ChangeType.MOVED,
                    old=inserted_item.new,
                    new=inserted_item.new,
                    level=inserted_item.level,
                    old_index=deleted_item.old_index,
                    new_index=inserted_item.new_index,
                )
                break
    return rewritten
