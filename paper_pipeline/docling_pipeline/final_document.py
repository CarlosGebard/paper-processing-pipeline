from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paper_pipeline.artifacts import metadata_path_for_base_name

from .text_cleanup import clean_definition_like_text


def extract_source_base_name(source: dict[str, Any] | None) -> str | None:
    if not isinstance(source, dict):
        return None

    source_name = str(source.get("name", "")).strip()
    if not source_name:
        return None

    return Path(source_name).stem or None


def load_metadata(source: dict[str, Any] | None, metadata_dir: Path | None = None) -> dict[str, Any]:
    base_name = extract_source_base_name(source)
    if not base_name or metadata_dir is None:
        return {}

    metadata_path = metadata_path_for_base_name(base_name, metadata_dir=metadata_dir)
    if metadata_path is None:
        return {}

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
        return payload["metadata"]
    if isinstance(payload, dict):
        return payload
    return {}


def simplify_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    simplified: list[dict[str, Any]] = []

    for section in sections:
        subsection_list = section.get("subsections", [])
        simplified.append(
            {
                "title": section.get("title", ""),
                "level": section.get("level", 1),
                "text": clean_definition_like_text(str(section.get("text", ""))),
                "subsections": simplify_sections(subsection_list if isinstance(subsection_list, list) else []),
            }
        )

    return simplified


def build_final_document(
    llm_filtered_document: dict[str, Any],
    metadata_dir: Path | None = None,
) -> dict[str, Any]:
    source = llm_filtered_document.get("source")
    metadata = load_metadata(source, metadata_dir=metadata_dir)
    sections = llm_filtered_document.get("sections", [])

    if not isinstance(sections, list):
        raise ValueError("El llm.filtered.json no contiene una lista válida en 'sections'.")

    return {
        "schema_name": "FinalPaperSectionsDocument",
        "version": "0.1.0",
        "paper": {
            "paper_id": metadata.get("paperId"),
            "title": metadata.get("title") or llm_filtered_document.get("paper_title"),
            "year": metadata.get("year"),
            "doi": metadata.get("doi"),
            "citation_count": metadata.get("citationCount"),
            "authors": metadata.get("authors", []),
            "pdf_url": metadata.get("pdf_url"),
        },
        "sections": simplify_sections(sections),
    }
