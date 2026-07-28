# =============================================================================
# File: language.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Optional language detection for OcrSegment.language (OCR P3).
# Responsibilities:
#   - Detect ISO 639-1 language codes via langdetect with timeout
#   - Document-level default (fast) or optional per-segment refine
# Dependencies:
#   - langdetect (optional at runtime); app.core.config.Settings
# Public Exports:
#   - annotate_segment_languages
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: Failures → language=None; must not add >10% pipeline cost
#   when using document-level mode (default).
# =============================================================================

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

    from .models import OcrSegment

_SAMPLE_CHARS = 3000
_LANGDETECT_SEED = 0


def annotate_segment_languages(
    segments: list[OcrSegment],
    *,
    settings: Settings | None = None,
) -> list[OcrSegment]:
    """Attach ``language`` to each segment; never raises on detection failure."""
    if not segments:
        return segments

    from app.core.config import get_settings

    cfg = settings or get_settings()
    if not cfg.ocr_language_detection_enabled:
        return segments

    sample_parts: list[str] = []
    size = 0
    for seg in segments:
        sample_parts.append(seg.text)
        size += len(seg.text)
        if size >= _SAMPLE_CHARS:
            break
    sample = " ".join(sample_parts)[:_SAMPLE_CHARS]
    doc_lang = _detect_language(
        sample,
        min_chars=cfg.ocr_language_min_chars,
        timeout_seconds=cfg.ocr_language_timeout_seconds,
    )

    out: list[OcrSegment] = []
    for seg in segments:
        lang = doc_lang
        if (
            cfg.ocr_language_detect_per_segment
            and len(seg.text) >= cfg.ocr_language_min_chars
        ):
            detected = _detect_language(
                seg.text,
                min_chars=cfg.ocr_language_min_chars,
                timeout_seconds=cfg.ocr_language_timeout_seconds,
            )
            if detected:
                lang = detected
        if lang == seg.language:
            out.append(seg)
            continue
        out.append(
            type(seg)(
                text=seg.text,
                order_index=seg.order_index,
                page_number=seg.page_number,
                section=seg.section,
                heading_level=seg.heading_level,
                block_type=seg.block_type,
                bbox=seg.bbox,
                language=lang,
                font_size=seg.font_size,
                font_name=seg.font_name,
                is_bold=seg.is_bold,
                section_index=seg.section_index,
            )
        )
    return out


def _detect_language(
    text: str,
    *,
    min_chars: int,
    timeout_seconds: float,
) -> str | None:
    """Return ISO 639-1 code or None. Swallows all detection errors/timeouts."""
    cleaned = (text or "").strip()
    if len(cleaned) < min_chars:
        return None

    try:
        from langdetect import DetectorFactory, detect
        from langdetect.lang_detect_exception import LangDetectException
    except ImportError:
        return None

    DetectorFactory.seed = _LANGDETECT_SEED

    def _run() -> str | None:
        try:
            code = detect(cleaned)
        except LangDetectException:
            return None
        except Exception:
            return None
        return str(code) if code else None

    # Fast path: langdetect is typically <10ms after import. Avoid flaky
    # ThreadPool timeouts on cold CI/Windows unless timeout is explicitly low.
    if timeout_seconds <= 0 or timeout_seconds >= 0.2:
        return _run()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeout:
            future.cancel()
            return None
        except Exception:
            return None
