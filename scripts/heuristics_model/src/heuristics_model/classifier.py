from __future__ import annotations

from .dictionaries import MAIN_SECTIONS, SECTION_PREFIX_PATTERNS, SUBSECTIONS
from .models import ClassifiedHeading
from .normalization import is_likely_false_heading


def _infer_section_by_prefix(normalized_heading: str) -> str | None:
    for canonical, patterns in SECTION_PREFIX_PATTERNS.items():
        for pattern in patterns:
            if normalized_heading == pattern:
                return canonical
            if normalized_heading.startswith(f"{pattern} "):
                return canonical
    return None


def classify_heading(normalized_heading: str, level: int, raw_heading: str) -> ClassifiedHeading:
    rules: list[str] = []

    if is_likely_false_heading(raw_heading=raw_heading, normalized_heading=normalized_heading):
        rules.append("false_heading_validation")
        return ClassifiedHeading(role="text", canonical_label=None, applied_rules=rules)

    if normalized_heading in MAIN_SECTIONS:
        rules.append("main_section_dictionary")
        return ClassifiedHeading(
            role="section",
            canonical_label=MAIN_SECTIONS[normalized_heading],
            applied_rules=rules,
        )

    inferred = _infer_section_by_prefix(normalized_heading)
    if inferred is not None:
        rules.append("main_section_prefix")
        return ClassifiedHeading(role="section", canonical_label=inferred, applied_rules=rules)

    if normalized_heading in SUBSECTIONS:
        rules.append("subsection_dictionary")
        return ClassifiedHeading(role="subsection", canonical_label=normalized_heading, applied_rules=rules)

    if level == 1:
        rules.append("fallback_level_1")
        return ClassifiedHeading(role="section", canonical_label=normalized_heading, applied_rules=rules)

    if level in (2, 3):
        rules.append("fallback_level_2_3")
        return ClassifiedHeading(role="subsection", canonical_label=normalized_heading, applied_rules=rules)

    rules.append("fallback_text")
    return ClassifiedHeading(role="text", canonical_label=None, applied_rules=rules)
