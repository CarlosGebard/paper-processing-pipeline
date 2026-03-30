from __future__ import annotations

import re


DEFINITION_EQ_PATTERN = re.compile(
    r"^(?:[A-Z][A-Z0-9\-]{1,20}\s*=\s*[^;]+)(?:;\s*[A-Z][A-Z0-9\-]{1,20}\s*=\s*[^;]+){1,}$"
)
LEADING_MARKER_PATTERN = re.compile(r"^(?:[-*•\u2020\u2021]+\s*)+")
LABELED_DEFINITION_PATTERN = re.compile(
    r"^(patient or population|setting|intervention|comparison|risk of bias|publication bias|imprecision|indirectness|inconsistency)\s*:",
    re.IGNORECASE,
)


def normalize_block(block: str) -> str:
    text = " ".join(block.split()).strip()
    return LEADING_MARKER_PATTERN.sub("", text)


def is_definition_like_block(block: str) -> bool:
    normalized = normalize_block(block)
    if not normalized:
        return False

    if DEFINITION_EQ_PATTERN.match(normalized):
        return True

    if LABELED_DEFINITION_PATTERN.match(normalized):
        return True

    colon_count = normalized.count(":")
    equals_count = normalized.count("=")

    if equals_count >= 2:
        return True

    if colon_count >= 2 and len(normalized.split()) <= 45:
        return True

    return False


def clean_definition_like_text(text: str) -> str:
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    kept_blocks = [block for block in blocks if not is_definition_like_block(block)]
    return "\n\n".join(kept_blocks)
