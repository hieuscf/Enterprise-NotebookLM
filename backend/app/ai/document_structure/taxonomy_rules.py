# =============================================================================
# File: taxonomy_rules.py
# Module/Service: Legal Risk Taxonomy (FR8 / TASK-CMP-07)
# Layer: Service
# Purpose: Compiled VN+EN phrase registry for the 14 canonical categories.
# Responsibilities:
#   - Phrase / keyword / negative patterns per category
#   - Independent rule_id for audit; no article-number shortcuts
# Dependencies:
#   - stdlib re; taxonomy_types.RiskCategory
# Public Exports:
#   - TaxonomyRule, TAXONOMY_RULES, rules_for, compile_pattern
# Database/Table: N/A
# Related Modules: taxonomy_engine
# Important Notes: Patterns match fold_ocr_text (no diacritics). 0 LLM.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ai.document_structure.taxonomy_types import RiskCategory


def compile_pattern(raw: str) -> re.Pattern[str]:
    return re.compile(raw, re.I)


@dataclass(frozen=True, slots=True)
class TaxonomyRule:
    """One deterministic phrase rule. Testable in isolation."""

    rule_id: str
    category: RiskCategory
    patterns: tuple[re.Pattern[str], ...]
    weight: float
    negatives: tuple[re.Pattern[str], ...] = ()

    def match(self, folded: str) -> str | None:
        if not folded:
            return None
        if any(item.search(folded) for item in self.negatives):
            return None
        for pattern in self.patterns:
            hit = pattern.search(folded)
            if hit:
                return hit.group(0).strip()
        return None


def _rule(
    rule_id: str,
    category: RiskCategory,
    patterns: tuple[str, ...],
    *,
    weight: float = 1.0,
    negatives: tuple[str, ...] = (),
) -> TaxonomyRule:
    return TaxonomyRule(
        rule_id=rule_id,
        category=category,
        patterns=tuple(compile_pattern(item) for item in patterns),
        weight=weight,
        negatives=tuple(compile_pattern(item) for item in negatives),
    )


_FINANCIAL_ID = (
    r"\b(?:so|so hieu|agreement no\.?|hop dong so|hd)[\s\-./]*\d",
)

TAXONOMY_RULES: tuple[TaxonomyRule, ...] = (
    # --- LIABILITY ---
    _rule(
        "liability.cap",
        RiskCategory.LIABILITY,
        (
            r"limitation of liability",
            r"liability\s+(?:cap|shall not exceed|will not exceed)",
            r"(?:aggregate|maximum|max(?:imum)?)\s+liability",
            r"damages?\s+cap",
            r"gioi han\s+(?:trach nhiem|boi thuong)",
            r"trach nhiem\s+(?:boi thuong|toi da)",
            r"tong trach nhiem",
            r"khong vuot qua.{0,40}trach nhiem|trach nhiem.{0,40}khong vuot qua",
        ),
    ),
    _rule(
        "liability.limitation",
        RiskCategory.LIABILITY,
        (
            r"consequential damages",
            r"indirect damages",
            r"liability exclusion",
            r"thiet hai gian tiep",
            r"khong chiu trach nhiem",
            r"loai tru trach nhiem",
        ),
    ),
    _rule(
        "liability.general",
        RiskCategory.LIABILITY,
        (
            r"\bindemnit(?:y|ies|ification)\b",
            r"\bliabilit(?:y|ies)\b",
            r"boi thuong",
        ),
        weight=0.78,
    ),
    # --- TERMINATION ---
    _rule(
        "termination.notice",
        RiskCategory.TERMINATION,
        (
            r"notice of termination",
            r"termination\s+(?:notice|period|right|event)",
            r"thong bao cham dut",
            r"cham dut.{0,24}thong bao|thong bao.{0,24}cham dut",
        ),
    ),
    _rule(
        "termination.right",
        RiskCategory.TERMINATION,
        (
            r"termination for (?:convenience|cause)",
            r"early termination",
            r"right to terminate",
            r"(?:may|shall)\s+terminate",
            r"quyen cham dut",
            r"don phuong cham dut",
            r"cham dut hop dong",
            r"cham dut trai",
        ),
    ),
    _rule(
        "termination.general",
        RiskCategory.TERMINATION,
        (
            r"\bterminat(?:e|ion|ed|ing)\b",
            r"\bcham dut\b",
        ),
        weight=0.82,
    ),
    # --- PAYMENT ---
    _rule(
        "payment.schedule",
        RiskCategory.PAYMENT,
        (
            r"payment schedule",
            r"milestone payment",
            r"installment",
            r"advance payment",
            r"lich thanh toan",
            r"thanh toan:\s",
        ),
    ),
    _rule(
        "payment.obligation",
        RiskCategory.PAYMENT,
        (
            r"payment shall be made",
            r"outstanding payments?",
            r"payment (?:terms?|obligation|deadline|due)",
            r"late payment",
            r"\binvoice\b",
            r"nghia vu thanh toan",
            r"thoi han thanh toan",
            r"\bthanh toan\b",
            r"\bpayments?\b",
        ),
        negatives=(r"khoan thanh toan dau tien",),
    ),
    # --- CONTRACT_TERM ---
    _rule(
        "contract_term.duration",
        RiskCategory.CONTRACT_TERM,
        (
            r"thoi han hop dong",
            r"thoi han thuc hien",
            r"term of this agreement",
            r"contract term",
            r"effective period",
            r"automatic renewal",
            r"\brenewal period\b",
            r"\bcommencement\b",
            r"\bexpir(?:y|ation|es)\b",
        ),
        negatives=(
            r"\bterminat",
            r"\bcham dut\b",
            r"thanh toan trong",
            r"payment (?:shall|must|within)",
        ),
    ),
    _rule(
        "contract_term.renewal",
        RiskCategory.CONTRACT_TERM,
        (
            r"\bgia han\b",
            r"\brenewal\b",
            r"hieu luc ke tu",
        ),
        weight=0.72,
        negatives=(r"\bterminat", r"\bcham dut\b", r"\bthanh toan\b"),
    ),
    _rule(
        "contract_term.weak_term",
        RiskCategory.CONTRACT_TERM,
        (r"(?<![a-z])term(?![a-z])", r"\bthoi han\b"),
        weight=0.55,
        negatives=(
            r"\bterminat",
            r"\bcham dut\b",
            r"\bthanh toan\b",
            r"\bpayment\b",
            r"\bbao mat\b",
            r"confidential",
            r"\bbao hanh\b",
            r"warranty",
            r"tranh chap",
            r"\bdispute\b",
        ),
    ),
    # --- FINANCIAL ---
    _rule(
        "financial.contract_value",
        RiskCategory.FINANCIAL,
        (
            r"gia tri hop dong",
            r"tong gia tri",
            r"contract (?:price|value)",
            r"total (?:contract )?(?:price|value|amount)",
        ),
        negatives=_FINANCIAL_ID,
    ),
    _rule(
        "financial.price",
        RiskCategory.FINANCIAL,
        (
            r"dieu chinh (?:don )?gia",
            r"price adjustment",
            r"\bdon gia\b",
            r"\bphi dich vu\b",
            r"financial (?:amount|obligation|threshold)",
        ),
        negatives=_FINANCIAL_ID,
    ),
    _rule(
        "financial.general",
        RiskCategory.FINANCIAL,
        (r"\b(?:price|fee|cost|currency)\b", r"\bphi\b"),
        weight=0.50,
        negatives=_FINANCIAL_ID + (r"phat sinh", r"trach nhiem", r"liability", r"penalty"),
    ),
    # --- CONFIDENTIALITY ---
    _rule(
        "confidentiality.period",
        RiskCategory.CONFIDENTIALITY,
        (
            r"confidentiality (?:period|obligations?)",
            r"nghia vu bao mat",
            r"thong tin mat",
            r"non-?disclosure",
            r"\bnda\b",
        ),
    ),
    _rule(
        "confidentiality.general",
        RiskCategory.CONFIDENTIALITY,
        (
            r"confidential(?:ity| information| material)?",
            r"\bbao mat\b",
            r"permitted disclosure",
            r"\bsecrecy\b",
        ),
        weight=0.80,
    ),
    # --- DATA_PROTECTION ---
    _rule(
        "data_protection.breach_notification",
        RiskCategory.DATA_PROTECTION,
        (
            r"breach notification",
            r"personal data breach",
            r"security incident",
            r"thong bao.{0,20}su co.{0,20}du lieu",
        ),
    ),
    _rule(
        "data_protection.general",
        RiskCategory.DATA_PROTECTION,
        (
            r"personal (?:data|information)",
            r"data protection",
            r"\bgdpr\b",
            r"data (?:processing|processor|controller|subject)",
            r"cross-?border transfer",
            r"du lieu ca nhan",
            r"bao ve du lieu",
            r"xu ly du lieu",
            r"quyen rieng tu",
            r"\bprivacy\b",
        ),
    ),
    # --- INTELLECTUAL_PROPERTY ---
    _rule(
        "ip.ownership",
        RiskCategory.INTELLECTUAL_PROPERTY,
        (
            r"intellectual property",
            r"so huu tri tue",
            r"background ip",
            r"foreground ip",
            r"ownership of (?:the )?deliverables",
            r"work product",
        ),
    ),
    _rule(
        "ip.general",
        RiskCategory.INTELLECTUAL_PROPERTY,
        (
            r"(?<![a-z])ip(?![a-z])",
            r"\bcopyright\b",
            r"\bpatent\b",
            r"\btrademark\b",
            r"trade secret",
            r"\blicens(?:e|ing)\b",
            r"\bban quyen\b",
            r"bang sang che",
            r"\bnhan hieu\b",
            r"\bcap phep\b",
        ),
        weight=0.80,
    ),
    # --- WARRANTY ---
    _rule(
        "warranty.period",
        RiskCategory.WARRANTY,
        (
            r"warranty period",
            r"thoi han bao hanh",
            r"thoi gian bao hanh",
            r"\bbao hanh\b",
        ),
    ),
    _rule(
        "warranty.general",
        RiskCategory.WARRANTY,
        (
            r"representation and warranty",
            r"\bwarranties\b",
            r"fitness for purpose",
            r"\bmerchantability\b",
            r"\bdefects?\b",
            r"\bguarantee\b",
        ),
        weight=0.78,
    ),
    # --- DISPUTE_RESOLUTION ---
    _rule(
        "dispute.arbitration",
        RiskCategory.DISPUTE_RESOLUTION,
        (
            r"\barbitration\b",
            r"arbitration (?:institution|rules)",
            r"\btrong tai\b",
            r"\bviac\b",
        ),
    ),
    _rule(
        "dispute.court",
        RiskCategory.DISPUTE_RESOLUTION,
        (
            r"courts? having jurisdiction",
            r"\bvenue\b",
            r"\btoa an\b",
            r"\bmediation\b",
            r"\bhoa giai\b",
        ),
    ),
    _rule(
        "dispute.negotiation",
        RiskCategory.DISPUTE_RESOLUTION,
        (
            r"dispute resolution",
            r"\bdisputes?\b",
            r"\btranh chap\b",
            r"giai quyet bang thuong luong",
        ),
    ),
    # --- PENALTY ---
    _rule(
        "penalty.rate",
        RiskCategory.PENALTY,
        (
            r"liquidated damages",
            r"late (?:payment )?penalty",
            r"contractual penalty",
            r"penalty (?:rate|cap)",
            r"phat vi pham",
            r"khoan phat",
            r"\bpenalty\b",
            r"\bfine\b",
        ),
    ),
    # --- SLA ---
    _rule(
        "sla.uptime",
        RiskCategory.SLA,
        (
            r"service level",
            r"\bsla\b",
            r"\buptime\b",
            r"service availability",
            r"ty le uptime",
            r"muc dich vu",
        ),
    ),
    _rule(
        "sla.response",
        RiskCategory.SLA,
        (
            r"response time",
            r"resolution time",
            r"service credit",
            r"incident response",
            r"support hours",
            r"performance target",
            r"thoi gian phan hoi",
            r"thoi gian xu ly",
        ),
    ),
    # --- GOVERNING_LAW ---
    _rule(
        "governing_law.applicable",
        RiskCategory.GOVERNING_LAW,
        (
            r"governing law",
            r"applicable law",
            r"governed by the laws?",
            r"laws of\s+\w+",
            r"luat ap dung",
            r"luat dieu chinh",
            r"dieu chinh boi phap luat",
            r"phap luat viet nam",
        ),
        negatives=(
            r"courts? having jurisdiction",
            r"toa an co tham quyen",
        ),
    ),
)


def rules_for(category: RiskCategory) -> tuple[TaxonomyRule, ...]:
    return tuple(rule for rule in TAXONOMY_RULES if rule.category is category)
