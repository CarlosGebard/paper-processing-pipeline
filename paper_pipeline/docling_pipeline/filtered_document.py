from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .final_document import load_metadata


SECTION_FILTER_RULES: dict[str, set[str]] = {
    "drop": {
        "abstract",
        "introduction",
        "discussion",
        "conclusion",
        "conclusions",
        "references",
    },
    "keep": {
        "method",
        "methods",
        "result",
        "results",
    },
}


def normalize_section_title(title: str) -> str:
    cleaned = " ".join(str(title).split()).strip().lower()
    for char in ":;,.!?()[]{}":
        cleaned = cleaned.replace(char, " ")
    return " ".join(cleaned.split())


def title_tokens(title: str) -> set[str]:
    normalized = normalize_section_title(title)
    return set(normalized.split()) if normalized else set()


def extract_source_base_name(logical_document: dict[str, Any]) -> str | None:
    source = logical_document.get("source", {})
    source_name = str(source.get("name", "")).strip()
    if not source_name:
        return None

    return Path(source_name).stem or None


def load_metadata_paper_title(
    logical_document: dict[str, Any],
    metadata_dir: Path | None = None,
) -> str | None:
    source = logical_document.get("source")
    metadata = load_metadata(source if isinstance(source, dict) else None, metadata_dir=metadata_dir)
    if not metadata:
        return None

    title = str(metadata.get("title", "")).strip()
    return title or None


def should_drop_section(title: str, paper_title: str | None = None) -> bool:
    normalized_title = normalize_section_title(title)
    if paper_title and normalized_title == normalize_section_title(paper_title):
        return True

    tokens = title_tokens(title)
    if not tokens:
        return False

    if tokens & SECTION_FILTER_RULES["keep"]:
        return False

    return bool(tokens & SECTION_FILTER_RULES["drop"])


def filter_sections(
    sections: list[dict[str, Any]],
    paper_title: str | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []

    for section in sections:
        subsection_list = section.get("subsections", [])
        if isinstance(subsection_list, list):
            section["subsections"] = filter_sections(
                subsection_list,
                paper_title=paper_title,
            )

        title = str(section.get("title", "")).strip()
        if should_drop_section(title, paper_title=paper_title):
            continue

        filtered.append(section)

    return filtered


def build_filtered_document(
    logical_document: dict[str, Any],
    metadata_dir: Path | None = None,
) -> dict[str, Any]:
    filtered_document = deepcopy(logical_document)
    sections = filtered_document.get("sections", [])

    if not isinstance(sections, list):
        raise ValueError("El documento lógico no contiene una lista válida en 'sections'.")

    paper_title = load_metadata_paper_title(
        logical_document,
        metadata_dir=metadata_dir,
    )

    filtered_document["schema_name"] = "FilteredCleanDoclingDocument"
    filtered_document["version"] = "0.1.0"
    filtered_document.pop("preamble", None)
    source = filtered_document.get("source")
    sections = filter_sections(
        sections,
        paper_title=paper_title,
    )
    filter_rules = {
        "drop": sorted(SECTION_FILTER_RULES["drop"]),
        "keep": sorted(SECTION_FILTER_RULES["keep"]),
        "policy": "drop_preamble_and_paper_title; drop_only_when_title_matches_rule; keep_ambiguous_sections",
    }

    return {
        "schema_name": filtered_document["schema_name"],
        "version": filtered_document["version"],
        "paper_title": paper_title,
        "source": source,
        "sections": sections,
        "excluded_furniture_count": filtered_document.get("excluded_furniture_count"),
        "filter_rules": filter_rules,
        "filtered_top_level_section_count": len(sections),
    }
