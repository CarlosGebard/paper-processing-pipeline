from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .raw_doc import is_furniture_item, iter_body_refs, resolve_ref


@dataclass
class HeadingEvent:
    title: str
    display_title: str
    raw_level: int | None
    signal: str
    logical_level: int = 1


@dataclass
class BlockEvent:
    block: dict[str, Any]


@dataclass
class LogicalSection:
    title: str
    display_title: str
    logical_level: int
    blocks: list[dict[str, Any]]
    sections: list["LogicalSection"]


def normalize_heading_text(text: str) -> str:
    clean = " ".join(text.split()).strip()
    if clean.isupper():
        return clean.title()
    return clean


def is_short_upper_heading(text: str) -> bool:
    stripped = " ".join(text.split()).strip()
    if not stripped or len(stripped) > 80:
        return False
    if stripped.endswith((".", ",", ";")):
        return False

    words = stripped.replace(":", "").split()
    if len(words) > 8:
        return False

    letters = [c for c in stripped if c.isalpha()]
    return bool(letters) and all(not c.islower() for c in letters)


def is_title_case_heading_candidate(text: str) -> bool:
    stripped = " ".join(text.split()).strip()
    if not stripped or len(stripped) > 80:
        return False
    if stripped.endswith((".", ",", ";", "?", "!")):
        return False

    words = stripped.replace(":", "").split()
    if not 1 <= len(words) <= 8:
        return False

    lower_words = {"and", "or", "of", "the", "in", "on", "for", "to", "with", "by"}
    title_like = 0
    for word in words:
        if word.lower() in lower_words:
            continue
        if word[:1].isupper():
            title_like += 1

    non_connector_words = [w for w in words if w.lower() not in lower_words]
    return title_like >= max(1, len(non_connector_words) - 1)


def text_heading_signal(item: dict[str, Any]) -> str | None:
    if item.get("label") != "text":
        return None

    text = str(item.get("text", "")).strip()
    if not text:
        return None

    if is_short_upper_heading(text):
        return "heuristic_uppercase_text"

    if is_title_case_heading_candidate(text):
        return "heuristic_titlecase_text"

    return None


def get_heading_signal(item: dict[str, Any]) -> str | None:
    if item.get("label") == "section_header":
        return "docling_section_header"
    return text_heading_signal(item)


def is_abstract_heading(text: str) -> bool:
    normalized = " ".join(text.split()).strip().upper()
    return normalized in {"ABSTRACT", "SUMMARY", "EXECUTIVE SUMMARY"}


def build_heading_event(item: dict[str, Any], signal: str) -> HeadingEvent:
    title = str(item.get("text", "")).strip()
    raw_level = item.get("level")
    return HeadingEvent(
        title=title,
        display_title=normalize_heading_text(title),
        raw_level=raw_level if isinstance(raw_level, int) else None,
        signal=signal,
    )


def build_text_block(
    item: dict[str, Any], heading_candidate_signal: str | None = None
) -> dict[str, Any]:
    block = {
        "type": "paragraph",
        "text": item.get("text", ""),
    }
    if heading_candidate_signal:
        block["heading_candidate"] = heading_candidate_signal
    return block


def build_list_block(doc: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for ref in iter_body_refs(group):
        child = resolve_ref(doc, ref)
        if not isinstance(child, dict):
            continue
        items.append({"text": child.get("text", "")})

    return {
        "type": "list",
        "items": items,
    }


def build_container_block(doc: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for ref in iter_body_refs(group):
        child = resolve_ref(doc, ref)
        if not isinstance(child, dict):
            continue
        items.append(
            {
                "type": child.get("label", "text"),
                "text": child.get("text", ""),
            }
        )

    return {
        "type": "container",
        "label": group.get("label"),
        "name": group.get("name"),
        "items": items,
    }


def build_picture_block() -> dict[str, Any]:
    return {"type": "picture"}


def _stringify_table_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("text", "value", "content", "label", "name"):
            text = _stringify_table_value(value.get(key))
            if text:
                return text
        for key in ("items", "cells", "children"):
            nested = value.get(key)
            if isinstance(nested, list):
                rendered = " ".join(part for part in (_stringify_table_value(item) for item in nested) if part)
                if rendered:
                    return rendered
        return ""
    if isinstance(value, list):
        return " ".join(part for part in (_stringify_table_value(item) for item in value) if part)
    return clean_text(str(value))


def _render_table_rows(table: dict[str, Any]) -> list[str]:
    rows = table.get("rows")
    if isinstance(rows, list):
        rendered_rows: list[str] = []
        for row in rows:
            if isinstance(row, dict):
                cells = row.get("cells") or row.get("items")
            else:
                cells = row
            if not isinstance(cells, list):
                continue
            rendered_cells = [_stringify_table_value(cell) for cell in cells]
            rendered_cells = [cell for cell in rendered_cells if cell]
            if rendered_cells:
                rendered_rows.append(" | ".join(rendered_cells))
        if rendered_rows:
            return rendered_rows

    data = table.get("data")
    if isinstance(data, list):
        rendered_rows = []
        for row in data:
            if not isinstance(row, list):
                continue
            rendered_cells = [_stringify_table_value(cell) for cell in row]
            rendered_cells = [cell for cell in rendered_cells if cell]
            if rendered_cells:
                rendered_rows.append(" | ".join(rendered_cells))
        if rendered_rows:
            return rendered_rows

    if isinstance(data, dict):
        table_cells = data.get("table_cells")
        if isinstance(table_cells, list):
            rendered_rows = _render_table_cell_grid(table_cells)
            if rendered_rows:
                return rendered_rows

    return []


def _render_table_cell_grid(table_cells: list[dict[str, Any]]) -> list[str]:
    max_row = 0
    max_col = 0
    for cell in table_cells:
        if not isinstance(cell, dict):
            continue
        max_row = max(max_row, int(cell.get("end_row_offset_idx") or 0))
        max_col = max(max_col, int(cell.get("end_col_offset_idx") or 0))

    if max_row <= 0 or max_col <= 0:
        return []

    grid = [["" for _ in range(max_col)] for _ in range(max_row)]
    for cell in table_cells:
        if not isinstance(cell, dict):
            continue
        row_idx = int(cell.get("start_row_offset_idx") or 0)
        col_idx = int(cell.get("start_col_offset_idx") or 0)
        if row_idx < 0 or col_idx < 0 or row_idx >= max_row or col_idx >= max_col:
            continue
        text = _stringify_table_value(cell.get("text"))
        if text:
            grid[row_idx][col_idx] = text

    rendered_rows: list[str] = []
    for row in grid:
        if not any(cell.strip() for cell in row):
            continue
        rendered_rows.append(" | ".join(cell.strip() for cell in row))
    return rendered_rows


def _resolve_table_ref_text(doc: dict[str, Any], refs: list[dict[str, Any]]) -> list[str]:
    resolved: list[str] = []
    for ref_obj in refs:
        if not isinstance(ref_obj, dict):
            continue
        ref = ref_obj.get("$ref")
        if not isinstance(ref, str):
            continue
        item = resolve_ref(doc, ref)
        if not isinstance(item, dict):
            continue
        text = _stringify_table_value(item.get("text"))
        if text:
            resolved.append(text)
    return resolved


def build_table_block(doc: dict[str, Any], table: dict[str, Any]) -> dict[str, Any]:
    caption_texts = _resolve_table_ref_text(doc, table.get("captions", []))
    footnote_texts = _resolve_table_ref_text(doc, table.get("footnotes", []))
    caption = (
        " ".join(caption_texts).strip()
        or _stringify_table_value(table.get("caption"))
        or _stringify_table_value(table.get("text"))
        or _stringify_table_value(table.get("name"))
        or _stringify_table_value(table.get("label"))
    )
    rows = _render_table_rows(table)
    parts: list[str] = []
    if caption:
        parts.append(f"Table: {caption}")
    parts.extend(rows)
    parts.extend(footnote_texts)
    return {
        "type": "table",
        "text": "\n".join(parts).strip() or "Table",
    }


def build_content_block(doc: dict[str, Any], ref: str, item: dict[str, Any]) -> dict[str, Any] | None:
    if ref.startswith("#/texts/"):
        return build_text_block(
            item,
            heading_candidate_signal=text_heading_signal(item),
        )

    if ref.startswith("#/groups/"):
        if item.get("label") == "list":
            return build_list_block(doc, item)
        return build_container_block(doc, item)

    if ref.startswith("#/pictures/"):
        return build_picture_block()

    if ref.startswith("#/tables/"):
        return build_table_block(doc, item)

    return None


def linearize_body(doc: dict[str, Any]) -> tuple[list[HeadingEvent | BlockEvent], list[dict[str, Any]]]:
    events: list[HeadingEvent | BlockEvent] = []
    excluded: list[dict[str, Any]] = []

    for ref in iter_body_refs(doc.get("body", {})):
        item = resolve_ref(doc, ref)
        if not isinstance(item, dict):
            continue

        if is_furniture_item(item):
            excluded.append(
                {
                    "label": item.get("label"),
                    "content_layer": item.get("content_layer"),
                    "text": item.get("text", ""),
                }
            )
            continue

        heading_signal = get_heading_signal(item)
        if heading_signal == "docling_section_header":
            events.append(build_heading_event(item, signal=heading_signal))
            continue

        block = build_content_block(doc, ref, item)
        if block is not None:
            events.append(BlockEvent(block=block))

    return events, excluded


def infer_heading_levels(events: list[HeadingEvent | BlockEvent]) -> None:
    abstract_mode = False

    for event in events:
        if not isinstance(event, HeadingEvent):
            continue

        if isinstance(event.raw_level, int) and event.raw_level > 1:
            event.logical_level = event.raw_level
            abstract_mode = False
            continue

        if is_abstract_heading(event.title):
            event.logical_level = 1
            abstract_mode = True
            continue

        if abstract_mode and event.signal == "docling_section_header" and is_short_upper_heading(event.title):
            event.logical_level = 2
            continue

        event.logical_level = 1
        abstract_mode = False


def make_section(event: HeadingEvent) -> LogicalSection:
    return LogicalSection(
        title=event.title,
        display_title=event.display_title,
        logical_level=event.logical_level,
        blocks=[],
        sections=[],
    )


def append_block_to_tree(
    root_blocks: list[dict[str, Any]],
    section_stack: list[LogicalSection],
    block: dict[str, Any],
) -> None:
    if section_stack:
        section_stack[-1].blocks.append(block)
        return
    root_blocks.append(block)


def clean_text(text: str) -> str:
    return " ".join(str(text).split()).strip()


def block_to_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")

    if block_type == "paragraph":
        return clean_text(block.get("text", ""))

    if block_type == "list":
        items = [clean_text(item.get("text", "")) for item in block.get("items", [])]
        items = [item for item in items if item]
        return "\n".join(f"- {item}" for item in items)

    if block_type == "container":
        parts = [clean_text(item.get("text", "")) for item in block.get("items", [])]
        parts = [part for part in parts if part]
        return "\n".join(parts)

    if block_type == "table":
        return str(block.get("text", "")).strip()

    return ""


def join_section_text(blocks: list[dict[str, Any]]) -> str:
    parts = [block_to_text(block) for block in blocks]
    parts = [part for part in parts if part]
    return "\n\n".join(parts)


def serialize_section(section: LogicalSection) -> dict[str, Any]:
    text = join_section_text(section.blocks)
    subsections = [serialize_section(child) for child in section.sections]
    return {
        "title": section.display_title or section.title,
        "level": section.logical_level,
        "text": text,
        "subsections": subsections,
    }


def build_logical_document(doc: dict[str, Any]) -> dict[str, Any]:
    events, excluded = linearize_body(doc)
    infer_heading_levels(events)

    root_blocks: list[dict[str, Any]] = []
    root_sections: list[LogicalSection] = []
    section_stack: list[LogicalSection] = []

    for event in events:
        if isinstance(event, HeadingEvent):
            section = make_section(event)

            while section_stack and section_stack[-1].logical_level >= section.logical_level:
                section_stack.pop()

            if section_stack:
                section_stack[-1].sections.append(section)
            else:
                root_sections.append(section)

            section_stack.append(section)
            continue

        append_block_to_tree(root_blocks, section_stack, event.block)

    preamble = join_section_text(root_blocks)

    return {
        "schema_name": "CleanDoclingDocument",
        "version": "0.2.0",
        "source": {
            "version": doc.get("version"),
            "name": doc.get("name"),
        },
        "preamble": preamble,
        "sections": [serialize_section(section) for section in root_sections],
        "excluded_furniture_count": len(excluded),
    }
