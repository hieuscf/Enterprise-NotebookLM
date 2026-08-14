# =============================================================================
# File: test_answer_sanitizer.py
# Module/Service: Chat Service / Citation Verification (FR4, FR5)
# Layer: Service
# Purpose: Unit tests for rewriting/stripping bracketed citation UUIDs in answers.
# Dependencies:
#   - pytest, app.services.chat.answer_sanitizer
# Database/Table: N/A
# Related Modules: answer_generator, message_service
# =============================================================================

from __future__ import annotations

from app.services.chat.answer_sanitizer import rewrite_inline_citation_markers

CID_1 = "84672b7c-7509-4848-aea5-dbaefcc4af53"
CID_2 = "ce483352-2f7e-4bd9-b914-c69eef97a27f"
CID_UNKNOWN = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_rewrites_verified_uuids_to_display_indexes() -> None:
    raw = (
        f"Yêu cầu Bên B báo cáo định kỳ [{CID_1}]. "
        f"Kiểm tra hệ thống [{CID_2}]."
    )
    out = rewrite_inline_citation_markers(raw, [CID_1, CID_2])
    assert CID_1 not in out
    assert CID_2 not in out
    assert "[1]" in out
    assert "[2]" in out
    assert "Yêu cầu Bên B báo cáo định kỳ [1]." in out


def test_strips_unknown_bracketed_uuids() -> None:
    raw = f"Nội dung có sẵn [{CID_UNKNOWN}]."
    out = rewrite_inline_citation_markers(raw, [CID_1])
    assert CID_UNKNOWN not in out
    assert "[" not in out or "[1]" not in out
    assert "Nội dung có sẵn." in out


def test_empty_answer_stays_empty() -> None:
    assert rewrite_inline_citation_markers("", [CID_1]) == ""
    assert rewrite_inline_citation_markers("   ", []) == ""


def test_strips_trailing_bracketed_uuid_list() -> None:
    leaked = (
        "Bên B phải báo cáo định kỳ. "
        "[ed4461c9-c07b-4c33-af2a-ddf3ae376034, "
        "6a15ed42-0217-4c94-8fe2-3fa9dfd4241f]"
    )
    out = rewrite_inline_citation_markers(leaked, [CID_1])
    assert "ed4461c9" not in out
    assert "6a15ed42" not in out
    assert "[" not in out
    assert out == "Bên B phải báo cáo định kỳ."


def test_uuid_list_strip_does_not_block_inline_index_rewrite() -> None:
    raw = (
        f"Yêu cầu báo cáo [{CID_1}]. "
        f"[{CID_1}, {CID_2}]"
    )
    out = rewrite_inline_citation_markers(raw, [CID_1, CID_2])
    assert CID_1 not in out
    assert CID_2 not in out
    assert "Yêu cầu báo cáo [1]." in out
    assert f"[{CID_1}, {CID_2}]" not in out
