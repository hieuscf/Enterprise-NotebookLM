# =============================================================================
# File: metadata_registry.py
# Module/Service: Query Router — Metadata Branch (FR11)
# Layer: Service
# Purpose: Whitelist MetadataRule registry (patterns → repository_method + template).
# Responsibilities:
#   - Match normalized queries to fixed intents (no text-to-SQL)
# Dependencies:
#   - stdlib re, templates keys
# Public Exports:
#   - MetadataRule, MetadataMatch, MetadataRegistry, DEFAULT_METADATA_RULES
# Database/Table: N/A
# Related Modules: handlers.metadata_handler
# Important Notes: Unknown match → complex downgrade (never invent SQL).
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.enums import FileType
from app.services.query_router.normalizer import normalize_query

_FILE_TYPE_ALIASES: tuple[tuple[re.Pattern[str], FileType], ...] = (
    (re.compile(r"\bpdfs?\b", re.IGNORECASE), FileType.pdf),
    (re.compile(r"\bdocx?\b", re.IGNORECASE), FileType.docx),
    (re.compile(r"\bxlsx?\b", re.IGNORECASE), FileType.xlsx),
    (re.compile(r"\bpptx?\b", re.IGNORECASE), FileType.pptx),
    (re.compile(r"\btxts?\b|\btext\s+files?\b", re.IGNORECASE), FileType.txt),
)

_UNSUPPORTED = re.compile(
    r"(?:\btags?\b|thống\s*kê\s*tag|tag\s*stats)",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True, slots=True)
class MetadataRule:
    """One whitelist metadata intent mapped to a fixed repository method."""

    intent: str
    patterns: tuple[str, ...]
    repository_method: str
    template: str
    priority: int = 50
    keywords: tuple[str, ...] = ()
    needs_file_type: bool = False
    template_en: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataMatch:
    """Result of matching a query against the metadata registry."""

    rule: MetadataRule
    file_type: FileType | None = None
    prefer_english: bool = False


DEFAULT_METADATA_RULES: tuple[MetadataRule, ...] = (
    MetadataRule(
        intent="count_members",
        priority=120,
        patterns=(
            r"(?:đếm|có\s*bao\s*nhiêu|số\s*lượng|tổng\s*số).{0,40}(?:thành\s*viên|member)",
            r"(?:how\s*many|number\s*of|count).{0,40}members?",
        ),
        keywords=("count members", "how many members"),
        repository_method="count_members",
        template="count_members_vi",
        template_en="count_members_en",
    ),
    MetadataRule(
        intent="stats_file_type",
        priority=110,
        patterns=(
            r"thống\s*kê.{0,40}(?:loại|file\s*type|kiểu\s*file)",
            r"stats?(?:\s*by)?\s*file\s*type",
            r"count\s*by\s*(?:file\s*)?type",
        ),
        keywords=("file type stats", "workspace statistics"),
        repository_method="stats_by_file_type",
        template="stats_file_type_vi",
        template_en="stats_file_type_en",
    ),
    MetadataRule(
        intent="document_owner",
        priority=105,
        patterns=(
            r"\b(who\s+uploaded|uploaded\s+by)\b",
            r"\b(ai\s+upload|ai\s+đã\s+upload|người\s+upload)\b",
        ),
        keywords=("who uploaded this file", "ai upload file này"),
        repository_method="document_owner",
        template="document_owner_vi",
        template_en="document_owner_en",
    ),
    MetadataRule(
        intent="latest_documents",
        priority=100,
        patterns=(
            r"\b(latest|newest|most\s+recent)\b.*\b(document|documents|file|files)\b",
            r"\b(file|tài\s+liệu)\s+(mới\s+nhất)\b",
            r"\b(mới\s+nhất)\b.*\b(file|tài\s+liệu)\b",
            r"recent\s*uploads?",
        ),
        keywords=("latest documents", "file mới nhất", "tài liệu mới nhất"),
        repository_method="latest_documents",
        template="latest_documents_vi",
        template_en="latest_documents_en",
    ),
    MetadataRule(
        intent="oldest_documents",
        priority=100,
        patterns=(
            r"\b(oldest|earliest)\b.*\b(document|documents|file|files)\b",
            r"\b(file|tài\s+liệu)\s+(cũ\s+nhất)\b",
            r"\b(cũ\s+nhất)\b.*\b(file|tài\s+liệu)\b",
        ),
        keywords=("oldest files", "oldest documents", "file cũ nhất"),
        repository_method="oldest_documents",
        template="oldest_documents_vi",
        template_en="oldest_documents_en",
    ),
    MetadataRule(
        intent="count_pdf",
        priority=95,
        patterns=(
            r"(?:how\s*many|count|number\s*of).{0,20}pdfs?",
            r"(?:có\s*)?(?:bao\s*nhiêu|mấy).{0,20}pdf",
        ),
        keywords=("count pdf", "how many pdfs", "có bao nhiêu pdf"),
        repository_method="count_pdf",
        template="count_pdf_vi",
        template_en="count_pdf_en",
    ),
    MetadataRule(
        intent="count_documents",
        priority=90,
        patterns=(
            r"(?:có\s*)?bao\s*nhiêu\s*(?:tài\s*liệu|document|file)",
            r"(?:đếm|số\s*lượng|tổng\s*số)\s*(?:tài\s*liệu|document|file)",
            r"how\s*many\s*(?:documents?|files?)",
            r"number\s*of\s*(?:documents?|files?)",
            r"count\s*(?:the\s*)?(?:documents?|files?)",
        ),
        keywords=("how many documents", "count documents", "có bao nhiêu tài liệu"),
        repository_method="count_documents",
        template="count_documents_vi",
        template_en="count_documents_en",
        needs_file_type=True,
    ),
    MetadataRule(
        intent="list_documents",
        priority=80,
        patterns=(
            r"liệt\s*kê\s*(?:tài\s*liệu|document|file)?",
            r"danh\s*sách\s*(?:tài\s*liệu|document|file|pdf)?",
            r"list\s*(?:all\s*)?(?:documents?|files?)?",
            r"show\s*all\s*(?:documents?|files?|pdfs?)?",
            r"display\s*(?:files?|documents?)",
        ),
        keywords=("list documents", "show all files", "danh sách tài liệu", "danh sách pdf"),
        repository_method="list_documents",
        template="list_documents_vi",
        template_en="list_documents_en",
        needs_file_type=True,
    ),
    MetadataRule(
        intent="count_chunks",
        priority=70,
        patterns=(r"(?:how\s*many|count|bao\s*nhiêu).{0,20}chunks?",),
        keywords=("count chunks", "how many chunks"),
        repository_method="count_chunks",
        template="count_chunks_vi",
        template_en="count_chunks_en",
    ),
    MetadataRule(
        intent="count_pages",
        priority=70,
        patterns=(r"(?:how\s*many|count|bao\s*nhiêu).{0,20}pages?",),
        keywords=("count pages", "how many pages"),
        repository_method="count_pages",
        template="count_pages_vi",
        template_en="count_pages_en",
    ),
)


def detect_file_type(query: str) -> FileType | None:
    """Extract a single file type mention from ``query``, if any."""
    for pattern, ft in _FILE_TYPE_ALIASES:
        if pattern.search(query):
            return ft
    return None


def _looks_english(normalized: str) -> bool:
    return bool(re.search(r"\b(how|many|list|show|count|latest|oldest|who|what)\b", normalized))


@dataclass
class MetadataRegistry:
    """Priority-ordered whitelist of ``MetadataRule`` objects."""

    rules: tuple[MetadataRule, ...] = field(default_factory=lambda: DEFAULT_METADATA_RULES)

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.rules, key=lambda r: r.priority, reverse=True))
        object.__setattr__(self, "rules", ordered)
        self._compiled: dict[str, tuple[re.Pattern[str], ...]] = {
            rule.intent: tuple(
                re.compile(p, re.IGNORECASE | re.UNICODE) for p in rule.patterns if p
            )
            for rule in self.rules
        }

    def match(self, query_text: str) -> MetadataMatch | None:
        """Return the highest-priority whitelist match, or ``None``."""
        q = normalize_query(query_text)
        if not q:
            return None
        if _UNSUPPORTED.search(q):
            return None

        file_type = detect_file_type(q)
        prefer_english = _looks_english(q)

        for rule in self.rules:
            hit = False
            for compiled in self._compiled.get(rule.intent, ()):
                if compiled.search(q):
                    hit = True
                    break
            if not hit:
                for kw in rule.keywords:
                    if kw and kw in q:
                        hit = True
                        break
            if not hit:
                continue
            return MetadataMatch(
                rule=rule,
                file_type=file_type if rule.needs_file_type else (
                    FileType.pdf if rule.intent == "count_pdf" else file_type
                ),
                prefer_english=prefer_english,
            )
        return None
