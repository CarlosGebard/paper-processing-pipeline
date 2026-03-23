from __future__ import annotations

from pathlib import Path
from typing import Any


def normalize_errors(errors: Any) -> list[str]:
    if not errors:
        return []

    if isinstance(errors, list):
        return [str(e) for e in errors]

    return [str(errors)]


def normalize_timings(timings: Any) -> dict[str, Any]:
    if timings is None:
        return {}

    if isinstance(timings, dict):
        return {str(k): str(v) for k, v in timings.items()}

    if hasattr(timings, "items"):
        try:
            return {str(k): str(v) for k, v in timings.items()}
        except Exception:
            pass

    return {"raw": str(timings)}


def build_conversion_summary(
    result: Any,
    input_pdf: Path,
    raw_markdown: str,
    json_clean: dict[str, Any],
    logical_json: dict[str, Any],
    filtered_json: dict[str, Any],
) -> dict[str, Any]:
    errors = normalize_errors(getattr(result, "errors", None))
    timings = normalize_timings(getattr(result, "timings", None))
    pages = getattr(result, "pages", None)

    page_count = len(pages) if isinstance(pages, list) else None
    logical_sections = logical_json.get("sections", [])
    filtered_sections = filtered_json.get("sections", [])

    return {
        "input_file": str(input_pdf),
        "status": str(getattr(result, "status", None)),
        "ocr_enabled": False,
        "table_structure_enabled": True,
        "page_count": page_count,
        "has_errors": len(errors) > 0,
        "error_count": len(errors),
        "errors": errors,
        "timings": timings,
        "quality_signals": {
            "markdown_chars": len(raw_markdown),
            "markdown_lines": len(raw_markdown.splitlines()),
            "json_top_level_keys": list(json_clean.keys()),
            "logical_json_top_level_keys": list(logical_json.keys()),
            "logical_top_level_section_count": len(logical_sections),
            "filtered_json_top_level_keys": list(filtered_json.keys()),
            "filtered_top_level_section_count": len(filtered_sections),
            "empty_output": len(raw_markdown.strip()) == 0,
        },
    }
