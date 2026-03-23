from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .section_classifier import (
    DEFAULT_DOTENV_PATH,
    SectionCandidate,
    classify_sections_with_openai,
    get_env_value,
)


def assign_section_ids(
    sections: list[dict[str, Any]],
    prefix: str = "sec",
    counter: list[int] | None = None,
) -> list[dict[str, Any]]:
    if counter is None:
        counter = [0]

    assigned: list[dict[str, Any]] = []
    for section in sections:
        counter[0] += 1
        section_copy = deepcopy(section)
        section_copy["id"] = f"{prefix}_{counter[0]:03d}"

        subsections = section_copy.get("subsections", [])
        if isinstance(subsections, list):
            section_copy["subsections"] = assign_section_ids(subsections, prefix=prefix, counter=counter)

        assigned.append(section_copy)

    return assigned


def flatten_sections(sections: list[dict[str, Any]]) -> list[SectionCandidate]:
    flat: list[SectionCandidate] = []

    for section in sections:
        flat.append(
            SectionCandidate(
                id=str(section.get("id", "")).strip(),
                title=str(section.get("title", "")).strip(),
                level=int(section.get("level", 1)),
            )
        )

        subsections = section.get("subsections", [])
        if isinstance(subsections, list):
            flat.extend(flatten_sections(subsections))

    return flat


def apply_llm_decisions(
    sections: list[dict[str, Any]],
    decisions_by_id: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []

    for section in sections:
        section_id = str(section.get("id", "")).strip()
        decision = decisions_by_id.get(
            section_id,
            {"decision": "uncertain", "reason": "missing_decision"},
        )

        section_copy = deepcopy(section)
        subsection_list = section_copy.get("subsections", [])
        if isinstance(subsection_list, list):
            section_copy["subsections"] = apply_llm_decisions(subsection_list, decisions_by_id)

        if decision["decision"] == "drop":
            continue

        section_copy["llm_decision"] = decision["decision"]
        section_copy["llm_reason"] = decision["reason"]
        filtered.append(section_copy)

    return filtered


def build_llm_filtered_document(
    filtered_document: dict[str, Any],
    dotenv_path: str | Path = DEFAULT_DOTENV_PATH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    paper_title = str(filtered_document.get("paper_title", "")).strip()
    if not paper_title:
        raise ValueError("El filtered.json no contiene 'paper_title'.")

    sections = filtered_document.get("sections", [])
    if not isinstance(sections, list):
        raise ValueError("El filtered.json no contiene una lista válida en 'sections'.")

    assigned_sections = assign_section_ids(sections)
    candidates = flatten_sections(assigned_sections)
    decisions, raw_response = classify_sections_with_openai(
        paper_title=paper_title,
        sections=candidates,
        dotenv_path=dotenv_path,
    )
    model_name = get_env_value(
        "OPENAI_MODEL",
        default="gpt-5-mini",
        dotenv_path=dotenv_path,
    )

    decisions_by_id = {item["id"]: item for item in decisions}
    final_sections = apply_llm_decisions(assigned_sections, decisions_by_id)

    llm_filtered_document = {
        "schema_name": "LLMFilteredCleanDoclingDocument",
        "version": "0.1.0",
        "paper_title": paper_title,
        "source": filtered_document.get("source"),
        "classifier": {
            "provider": "openai",
            "model": model_name,
            "policy": "keep_on_uncertain",
            "prompt_version": "v1",
        },
        "section_decisions": decisions,
        "sections": final_sections,
        "llm_filtered_top_level_section_count": len(final_sections),
    }

    return llm_filtered_document, raw_response
