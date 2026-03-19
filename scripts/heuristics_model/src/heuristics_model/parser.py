from __future__ import annotations

from .models import Block, SourceSpan
from .normalization import normalize_heading


def parse_markdown(markdown_text: str) -> list[Block]:
    blocks: list[Block] = []
    current_heading: str | None = None
    current_level = 0
    current_lines: list[str] = []
    text_start_line = 1
    heading_line = 1

    def flush(end_line: int) -> None:
        nonlocal current_lines
        if not current_lines and current_heading is None:
            return

        text = "\n".join(current_lines).strip()
        start_line = heading_line if current_heading is not None else text_start_line
        block_end_line = max(start_line, end_line)
        blocks.append(
            Block(
                level=current_level,
                raw_heading=current_heading,
                normalized_heading=normalize_heading(current_heading) if current_heading else None,
                text=text,
                source_span=SourceSpan(start_line=start_line, end_line=block_end_line),
            )
        )
        current_lines = []

    for idx, line in enumerate(markdown_text.splitlines(), start=1):
        stripped = line.strip()
        level: int | None = None
        heading: str | None = None

        if stripped.startswith("### "):
            level = 3
            heading = stripped[4:]
        elif stripped.startswith("## "):
            level = 2
            heading = stripped[3:]
        elif stripped.startswith("# "):
            level = 1
            heading = stripped[2:]

        if heading is not None and level is not None:
            flush(end_line=idx - 1)
            current_heading = heading
            current_level = level
            heading_line = idx
            text_start_line = idx + 1
            continue

        current_lines.append(line)

    flush(end_line=max(1, len(markdown_text.splitlines())))
    return blocks
