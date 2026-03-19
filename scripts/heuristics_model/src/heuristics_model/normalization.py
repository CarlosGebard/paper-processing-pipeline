from __future__ import annotations

import re


_SECTION_NUMBER_RE = re.compile(
    r"^\s*(?:\(?\d+(?:\.\d+)*\)?|\(?[ivxlcdm]+\)?)[-.:)]?\s+",
    re.IGNORECASE,
)
_OUTER_PUNCT_RE = re.compile(r"^[\W_]+|[\W_]+$")
_SPACES_RE = re.compile(r"\s+")
_CAPTION_PREFIX_RE = re.compile(r"^(?:figure|fig\.?|table|supp(?:lementary)?\s+figure)\s*\d+", re.IGNORECASE)
_VERB_TOKEN_RE = re.compile(
    r"\b(?:is|are|was|were|be|being|been|has|have|had|do|does|did|shows|showed|show|demonstrates|demonstrated|indicates|indicated|suggests|suggested|compare|compares|compared|comparing)\b",
    re.IGNORECASE,
)


def normalize_heading(raw: str) -> str:
    text = raw.strip().lower()
    text = _SECTION_NUMBER_RE.sub("", text)
    text = _OUTER_PUNCT_RE.sub("", text)
    text = _SPACES_RE.sub(" ", text)
    return text.strip()


def is_caption_like(text: str) -> bool:
    return bool(_CAPTION_PREFIX_RE.match(text.strip()))


def _count_likely_verbs(text: str) -> int:
    return len(_VERB_TOKEN_RE.findall(text))


def is_likely_false_heading(raw_heading: str, normalized_heading: str) -> bool:
    if len(normalized_heading) > 120:
        return True
    if raw_heading.strip().endswith((".", "?", "!")):
        return True
    if is_caption_like(raw_heading) or is_caption_like(normalized_heading):
        return True
    if _count_likely_verbs(normalized_heading) > 1:
        return True
    return False
