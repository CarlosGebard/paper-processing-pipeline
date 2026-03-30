from __future__ import annotations

from pathlib import Path
from typing import Any

from .text_cleanup import clean_definition_like_text
from .title_resolution import metadata_paper_title, require_metadata

MIN_SECTION_WORDS = 10


def count_words(text: str) -> int:
    return len(text.split()) if text.strip() else 0


def has_table_content(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return "Table:" in stripped


def should_keep_simplified_section(section: dict[str, Any]) -> bool:
    text = str(section.get("text", "") or "").strip()
    subsections = section.get("subsections", [])
    has_subsections = isinstance(subsections, list) and len(subsections) > 0
    if has_subsections:
        return True
    if has_table_content(text):
        return True
    return count_words(text) > MIN_SECTION_WORDS


def simplify_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    simplified: list[dict[str, Any]] = []

    for section in sections:
        subsection_list = section.get("subsections", [])
        simplified_section = {
            "title": section.get("title", ""),
            "level": section.get("level", 1),
            "text": clean_definition_like_text(str(section.get("text", ""))).strip(),
            "subsections": simplify_sections(subsection_list if isinstance(subsection_list, list) else []),
        }
        if should_keep_simplified_section(simplified_section):
            simplified.append(simplified_section)

    return simplified


def build_final_document(
    llm_filtered_document: dict[str, Any],
    metadata_dir: Path | None = None,
) -> dict[str, Any]:
    source = llm_filtered_document.get("source")
    metadata = require_metadata(source if isinstance(source, dict) else None, metadata_dir=metadata_dir)
    resolved_title = metadata_paper_title(
        source if isinstance(source, dict) else None,
        metadata_dir=metadata_dir,
    )
    sections = llm_filtered_document.get("sections", [])

    if not isinstance(sections, list):
        raise ValueError("El llm.filtered.json no contiene una lista válida en 'sections'.")

    return {
        "schema_name": "FinalPaperSectionsDocument",
        "version": "0.1.0",
        "paper": {
            "paper_id": metadata.get("paperId"),
            "title": resolved_title,
            "year": metadata.get("year"),
            "doi": metadata.get("doi"),
            "citation_count": metadata.get("citationCount"),
            "authors": metadata.get("authors", []),
            "pdf_url": metadata.get("pdf_url"),
        },
        "sections": simplify_sections(sections),
    }
