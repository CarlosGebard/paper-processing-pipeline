from __future__ import annotations

from dataclasses import dataclass
import re

from .classifier import classify_heading
from .dictionaries import (
    CANONICAL_PAPER_ORDER,
    CUTOFF_SECTIONS,
    EDITORIAL_NOISE,
    PRIORITY_SECTIONS,
    SUPPLEMENTARY_SECTIONS,
)
from .models import DocumentStructure, IgnoredTable, SectionNode, SourceSpan, SubsectionNode, TextNode
from .normalization import is_caption_like
from .parser import parse_markdown

_MARKDOWN_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
_MARKDOWN_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
_PDF_COLUMN_SPLIT_RE = re.compile(r"\s{2,}")
_TABLE_SIGNAL_RE = re.compile(r"(?:\d|rr|ci|sd|se|p<|p=|not estimable)", re.IGNORECASE)
_EDITORIAL_PREFIX_RE = re.compile(
    r"^(?:funding|competing interests|transparency declaration|data sharing|contributors|accepted|systematic review registration|cite this as)\s*:",
    re.IGNORECASE,
)
_OPEN_ACCESS_PREFIX_RE = re.compile(r"^this is an open access article", re.IGNORECASE)
_REFERENCE_ITEM_RE = re.compile(r"^\s*(?:[-*]\s*)?\d+\s+[A-Za-z]")
_REFERENCE_BULLET_ITEM_RE = re.compile(r"^\s*[-*]\s*\d+\s+")
_REFERENCE_BULLET_FRAGMENT_RE = re.compile(r"^\s*[-*]\s*\d{3,4}(?:/\d{1,4})+\)\s*:")
_REFERENCE_BULLET_CONTINUATION_RE = re.compile(r"^\s*[-*]\s+.*doi:", re.IGNORECASE)
_EDITORIAL_TEXT_PREFIX_RE = re.compile(
    r"^(?:this review is one of a set of reviews conducted by|members of the pufah group are|we thank all the authors of primary studies who kindly replied to our queries)",
    re.IGNORECASE,
)
_ABSTRACT_STRUCTURED_HEADINGS: set[str] = {
    "objective",
    "design",
    "data sources",
    "eligibility criteria",
    "data synthesis",
    "results",
    "conclusions",
    "systematic review registration",
}
_EDITORIAL_HEADING_PREFIXES: tuple[str, ...] = (
    "cite this as",
    "accepted",
    "funding",
    "competing interests",
    "transparency declaration",
    "contributors",
)


@dataclass(slots=True)
class _StackItem:
    level: int
    role: str
    section: SectionNode
    subsection: SubsectionNode | None


SCIENTIFIC_CONTEXT_SECTIONS = PRIORITY_SECTIONS | {"conclusion"}


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _MARKDOWN_TABLE_LINE_RE.match(stripped):
        return True
    if _MARKDOWN_TABLE_SEPARATOR_RE.match(stripped):
        return True
    if stripped.lower().startswith("table ") and any(ch.isdigit() for ch in stripped):
        return True
    columns = [chunk.strip() for chunk in _PDF_COLUMN_SPLIT_RE.split(stripped) if chunk.strip()]
    if len(columns) >= 3 and len(columns) <= 8:
        signal_columns = sum(1 for col in columns if _TABLE_SIGNAL_RE.search(col))
        if signal_columns >= 2:
            return True
    return False


def _strip_tables(text: str, source_span: SourceSpan) -> tuple[str, list[IgnoredTable]]:
    kept_lines: list[str] = []
    ignored_tables: list[IgnoredTable] = []
    table_lines: list[tuple[int, str]] = []

    lines = text.splitlines()
    for offset, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if table_lines:
                start_offset = table_lines[0][0]
                end_offset = table_lines[-1][0]
                ignored_tables.append(
                    IgnoredTable(
                        text="\n".join(table_line for _, table_line in table_lines),
                        source_span=SourceSpan(
                            start_line=source_span.start_line + start_offset,
                            end_line=source_span.start_line + end_offset,
                        ),
                    )
                )
                table_lines = []
            kept_lines.append(line)
            continue
        if stripped == "<!-- image -->":
            if table_lines:
                table_lines.append((offset, line))
            continue
        if is_caption_like(stripped):
            table_lines.append((offset, line))
            continue
        if stripped.lower().startswith("fig "):
            continue
        if _is_table_line(line):
            table_lines.append((offset, line))
            continue

        if table_lines:
            start_offset = table_lines[0][0]
            end_offset = table_lines[-1][0]
            ignored_tables.append(
                IgnoredTable(
                    text="\n".join(table_line for _, table_line in table_lines),
                    source_span=SourceSpan(
                        start_line=source_span.start_line + start_offset,
                        end_line=source_span.start_line + end_offset,
                    ),
                )
            )
            table_lines = []
        kept_lines.append(line)

    if table_lines:
        start_offset = table_lines[0][0]
        end_offset = table_lines[-1][0]
        ignored_tables.append(
            IgnoredTable(
                text="\n".join(table_line for _, table_line in table_lines),
                source_span=SourceSpan(
                    start_line=source_span.start_line + start_offset,
                    end_line=source_span.start_line + end_offset,
                ),
            )
        )

    return "\n".join(kept_lines).strip(), ignored_tables


def _append_text(structure: DocumentStructure, content: list[TextNode], text: str, span: SourceSpan) -> None:
    cleaned, ignored_tables = _strip_tables(text, span)
    structure.ignored_tables.extend(ignored_tables)
    if not cleaned:
        return
    cleaned = _strip_inline_editorial_noise(cleaned)
    if not cleaned:
        return
    cleaned = _normalize_paragraph_breaks(cleaned)
    if not cleaned:
        return
    if _is_editorial_noise_text(cleaned):
        return
    content.append(TextNode(text=cleaned, source_span=span))


def _is_reference_like_line(stripped: str) -> bool:
    return (
        bool(_REFERENCE_BULLET_ITEM_RE.match(stripped))
        or bool(_REFERENCE_BULLET_FRAGMENT_RE.match(stripped))
        or bool(_REFERENCE_BULLET_CONTINUATION_RE.match(stripped))
    )


def _strip_inline_editorial_noise(text: str) -> str:
    kept_lines: list[str] = []
    previous_was_reference = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept_lines.append(line)
            previous_was_reference = False
            continue
        if _EDITORIAL_PREFIX_RE.match(stripped):
            previous_was_reference = False
            continue
        if _OPEN_ACCESS_PREFIX_RE.match(stripped):
            previous_was_reference = False
            continue
        if _EDITORIAL_TEXT_PREFIX_RE.match(stripped):
            previous_was_reference = False
            continue
        if _is_reference_like_line(stripped):
            previous_was_reference = True
            continue
        if previous_was_reference and stripped.startswith(("-", "*")):
            continue
        kept_lines.append(line)
        previous_was_reference = False
    return "\n".join(kept_lines).strip()


def _is_editorial_noise_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True

    first_line = stripped.splitlines()[0].strip()
    if _EDITORIAL_PREFIX_RE.match(first_line):
        return True
    if _OPEN_ACCESS_PREFIX_RE.match(first_line):
        return True
    if _EDITORIAL_TEXT_PREFIX_RE.match(first_line):
        return True

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    reference_like = sum(1 for line in lines if _REFERENCE_ITEM_RE.match(line))
    return reference_like >= 3 and (reference_like / len(lines)) >= 0.6


def _is_structural_line(stripped: str) -> bool:
    if not stripped:
        return True
    if stripped.startswith(("#", "|", "<!--", "```")):
        return True
    if stripped.startswith(("- ", "* ")):
        return True
    if re.match(r"^\d+[.)]\s+", stripped):
        return True
    return False


def _normalize_paragraph_breaks(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return ""

    normalized_lines: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        merged: list[str] = []
        for raw_line in paragraph:
            current = raw_line.strip()
            if not current:
                continue
            if not merged:
                merged.append(current)
                continue
            previous = merged[-1].strip()
            if _is_structural_line(previous) or _is_structural_line(current):
                merged.append(current)
            else:
                merged[-1] = f"{previous} {current}"
        normalized_lines.extend(merged)

    for line in lines:
        if line.strip():
            paragraph.append(line)
            continue
        flush_paragraph()
        paragraph = []
        if normalized_lines and normalized_lines[-1] != "":
            normalized_lines.append("")

    flush_paragraph()
    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()
    return "\n".join(normalized_lines).strip()


def _reorder_sections(sections: list[SectionNode]) -> list[SectionNode]:
    by_title: dict[str, list[SectionNode]] = {}
    for section in sections:
        by_title.setdefault(section.title, []).append(section)

    ordered: list[SectionNode] = []
    handled: set[str] = set()
    canonical_without_references = tuple(
        title for title in CANONICAL_PAPER_ORDER if title != "references"
    )
    for canonical in canonical_without_references:
        for section in by_title.get(canonical, []):
            ordered.append(section)
        if canonical in by_title:
            handled.add(canonical)

    for section in sections:
        if section.title in handled:
            continue
        if section.title == "references":
            continue
        ordered.append(section)
        handled.add(section.title)

    for section in by_title.get("references", []):
        ordered.append(section)

    return ordered


def _pop_stack_for_heading(stack: list[_StackItem], new_level: int, new_role: str) -> None:
    if new_role == "section":
        while stack and stack[-1].level >= new_level:
            stack.pop()
        return

    # For subsection headings, keep a same-level parent section in stack.
    while stack:
        top = stack[-1]
        if top.role == "subsection" and top.level >= new_level:
            stack.pop()
            continue
        if top.role == "section" and top.level > new_level:
            stack.pop()
            continue
        break


def process_markdown(markdown_text: str) -> DocumentStructure:
    blocks = parse_markdown(markdown_text)
    structure = DocumentStructure()

    section_map: dict[str, SectionNode] = {}
    stack: list[_StackItem] = []
    in_abstract = False
    last_scientific_section: SectionNode | None = None

    for block in blocks:
        skip_current_block = False

        if block.raw_heading and block.normalized_heading:
            if block.normalized_heading.startswith(_EDITORIAL_HEADING_PREFIXES):
                continue

            if in_abstract and block.normalized_heading in _ABSTRACT_STRUCTURED_HEADINGS:
                section = section_map.get("abstract")
                if section is None:
                    section = SectionNode(title="abstract")
                    section_map["abstract"] = section
                    structure.sections.append(section)

                subsection = next(
                    (sub for sub in section.subsections if sub.title == block.normalized_heading),
                    None,
                )
                if subsection is None:
                    subsection = SubsectionNode(title=block.normalized_heading)
                    section.subsections.append(subsection)

                _pop_stack_for_heading(stack=stack, new_level=block.level, new_role="subsection")
                if not any(item.role == "section" and item.section.title == "abstract" for item in stack):
                    stack.append(_StackItem(level=max(1, block.level - 1), role="section", section=section, subsection=None))

                stack.append(
                    _StackItem(
                        level=block.level,
                        role="subsection",
                        section=section,
                        subsection=subsection,
                    )
                )
                skip_current_block = False
                if not block.text:
                    continue
                active_subsection = subsection
                _append_text(structure, active_subsection.content, block.text, block.source_span)
                continue

            classification = classify_heading(
                normalized_heading=block.normalized_heading,
                level=block.level,
                raw_heading=block.raw_heading,
            )

            label = classification.canonical_label
            if label in CUTOFF_SECTIONS:
                break

            if label in EDITORIAL_NOISE or label in SUPPLEMENTARY_SECTIONS:
                skip_current_block = True
            elif classification.role in {"section", "subsection"} and label:
                _pop_stack_for_heading(stack=stack, new_level=block.level, new_role=classification.role)

                if classification.role == "section":
                    section = section_map.get(label)
                    if section is None:
                        section = SectionNode(title=label)
                        section_map[label] = section
                        structure.sections.append(section)
                    stack.append(_StackItem(level=block.level, role="section", section=section, subsection=None))
                    in_abstract = label == "abstract"
                    if label in SCIENTIFIC_CONTEXT_SECTIONS:
                        last_scientific_section = section
                else:
                    parent_section = next((item.section for item in reversed(stack) if item.role == "section"), None)
                    if parent_section is None:
                        if last_scientific_section is not None:
                            parent_section = last_scientific_section
                            stack.append(
                                _StackItem(level=max(1, block.level - 1), role="section", section=parent_section, subsection=None)
                            )
                        else:
                            parent_section = section_map.get("unclassified")
                            if parent_section is None:
                                parent_section = SectionNode(title="unclassified")
                                section_map["unclassified"] = parent_section
                                structure.sections.append(parent_section)
                            stack.append(_StackItem(level=1, role="section", section=parent_section, subsection=None))

                    if in_abstract:
                        skip_current_block = True
                    else:
                        subsection = next(
                            (sub for sub in parent_section.subsections if sub.title == label),
                            None,
                        )
                        if subsection is None:
                            subsection = SubsectionNode(title=label)
                            parent_section.subsections.append(subsection)
                        stack.append(
                            _StackItem(
                                level=block.level,
                                role="subsection",
                                section=parent_section,
                                subsection=subsection,
                            )
                        )

        if skip_current_block or not block.text:
            continue

        active_subsection = next((item.subsection for item in reversed(stack) if item.subsection), None)
        active_section = next((item.section for item in reversed(stack) if item.role == "section"), None)

        if active_subsection is not None:
            _append_text(structure, active_subsection.content, block.text, block.source_span)
        elif active_section is not None:
            _append_text(structure, active_section.content, block.text, block.source_span)

    structure.sections = _reorder_sections(structure.sections)
    return structure
