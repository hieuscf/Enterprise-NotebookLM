# =============================================================================
# File: metadata_patterns.py
# Module/Service: Query Router — Query Classifier (FR11)
# Layer: Service
# Purpose: Registry of metadata PatternRule objects (VI + EN), not hard-coded regex.
# Responsibilities:
#   - Define PatternRule dataclass; ship default workspace/document listing rules
#   - Match normalized queries by priority (regex first, then keywords)
# Dependencies:
#   - stdlib re
# Public Exports:
#   - PatternRule, MetadataPatternRegistry, DEFAULT_METADATA_RULES
# Database/Table: N/A
# Related Modules: app.services.query_router.rule_classifier
# Important Notes: Add rules here without touching the classifier.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.query_router.models import MetadataMatchResult


@dataclass(frozen=True, slots=True)
class PatternRule:
    """One metadata classification rule with priority and match strategies.

    Args:
        name: Stable rule identifier (logged / returned in match result).
        priority: Higher wins when multiple rules match.
        regex: Compiled-ready regex strings matched against normalized text.
        keywords: Substring phrases matched against normalized text.
    """

    name: str
    priority: int
    regex: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()

    def compiled_regexes(self) -> tuple[re.Pattern[str], ...]:
        """Compile regex strings with IGNORECASE | UNICODE."""
        return tuple(
            re.compile(pattern, re.IGNORECASE | re.UNICODE)
            for pattern in self.regex
            if pattern
        )


# Default bilingual metadata rules — extend this tuple to add coverage.
DEFAULT_METADATA_RULES: tuple[PatternRule, ...] = (
    PatternRule(
        name="count_documents",
        priority=100,
        regex=(
            r"\b(how\s+many|count|number\s+of)\b.*\b(document|documents|file|files|"
            r"pdf|pdfs|invoice|invoices)\b",
            r"\b(có\s+bao\s+nhiêu|có\s+mấy|bao\s+nhiêu|tổng\s+số|số\s+lượng)\b.*"
            r"\b(tài\s+liệu|file|files|pdf|hóa\s+đơn|hoa\s+don)\b",
        ),
        keywords=(
            "how many documents",
            "how many files",
            "count documents",
            "count files",
            "count invoices",
            "number of documents",
            "number of files",
            "có bao nhiêu tài liệu",
            "có mấy file",
            "có mấy tài liệu",
            "bao nhiêu tài liệu",
            "tổng số tài liệu",
            "số lượng tài liệu",
        ),
    ),
    PatternRule(
        name="list_documents",
        priority=90,
        regex=(
            r"\b(list|show|display|enumerate)\b.*\b(document|documents|file|files|"
            r"pdf|pdfs|all)\b",
            r"\b(danh\s+sách|liệt\s+kê|hiển\s+thị|hien\s+thi)\b.*"
            r"\b(tài\s+liệu|file|files|pdf|pdfs|workspace)\b",
        ),
        keywords=(
            "list documents",
            "list files",
            "list all",
            "show all",
            "show all pdfs",
            "show all files",
            "display files",
            "display workspace",
            "danh sách tài liệu",
            "danh sách pdf",
            "liệt kê các pdf",
            "hiển thị workspace",
            "hiển thị tài liệu",
        ),
    ),
    PatternRule(
        name="latest_oldest",
        priority=85,
        regex=(
            r"\b(latest|newest|oldest|most\s+recent|earliest)\b.*"
            r"\b(document|documents|file|files)\b",
            r"\b(file|tài\s+liệu)\s+(mới\s+nhất|cũ\s+nhất)\b",
            r"\b(mới\s+nhất|cũ\s+nhất)\b.*\b(file|tài\s+liệu)\b",
            r"\btop\s+\d+\b.*\b(document|documents|file|files|tài\s+liệu)\b",
        ),
        keywords=(
            "latest documents",
            "latest files",
            "oldest files",
            "oldest documents",
            "newest files",
            "file mới nhất",
            "file cũ nhất",
            "tài liệu mới nhất",
            "tài liệu cũ nhất",
            "top 10 tài liệu",
        ),
    ),
    PatternRule(
        name="uploader_info",
        priority=80,
        regex=(
            r"\b(who\s+uploaded|uploaded\s+by|upload\s+by)\b",
            r"\b(ai\s+upload|ai\s+đã\s+upload|người\s+upload)\b",
        ),
        keywords=(
            "who uploaded this file",
            "who uploaded",
            "ai upload file này",
            "ai đã upload",
        ),
    ),
    PatternRule(
        name="workspace_stats",
        priority=70,
        regex=(
            r"\b(statistics|stats|thống\s+kê|thong\s+ke)\b",
            r"\b(workspace)\b.*\b(info|information|files|documents)\b",
        ),
        keywords=(
            "thống kê",
            "workspace stats",
            "document statistics",
        ),
    ),
)


@dataclass
class MetadataPatternRegistry:
    """Priority-ordered registry of ``PatternRule`` instances.

    Rules are sorted once at construction. Matching walks highest priority first
    and returns on the first hit (regex match preferred over keyword within a rule).
    """

    rules: tuple[PatternRule, ...] = field(default_factory=lambda: DEFAULT_METADATA_RULES)

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.rules, key=lambda r: r.priority, reverse=True))
        object.__setattr__(self, "rules", ordered)
        self._compiled: dict[str, tuple[re.Pattern[str], ...]] = {
            rule.name: rule.compiled_regexes() for rule in self.rules
        }

    def match(self, normalized_query: str) -> MetadataMatchResult:
        """Return the highest-priority metadata match for ``normalized_query``.

        Args:
            normalized_query: Already-normalized query text.

        Returns:
            ``MetadataMatchResult`` — ``matched=False`` when no rule hits.
        """
        q = (normalized_query or "").strip()
        if not q:
            return MetadataMatchResult(matched=False)

        for rule in self.rules:
            for compiled in self._compiled.get(rule.name, ()):
                m = compiled.search(q)
                if m:
                    return MetadataMatchResult(
                        matched=True,
                        rule_name=rule.name,
                        pattern=m.group(0),
                        priority=rule.priority,
                    )
            for keyword in rule.keywords:
                kw = keyword.strip().lower()
                if kw and kw in q:
                    return MetadataMatchResult(
                        matched=True,
                        rule_name=rule.name,
                        pattern=kw,
                        priority=rule.priority,
                    )
        return MetadataMatchResult(matched=False)
