from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .chunking import build_chunks
from .pipeline import process_markdown
from .rendering import render_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Heuristic section classifier for Docling Markdown")
    parser.add_argument("input", type=Path, help="Path to markdown input")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Primary output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file path; defaults to stdout",
    )
    args = parser.parse_args()

    markdown_text = args.input.read_text(encoding="utf-8")
    structure = process_markdown(markdown_text)

    if args.format == "json":
        rendered_output = json.dumps(
            {
                "structure": asdict(structure),
                "chunks": build_chunks(structure),
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        rendered_output = render_markdown(structure)

    if args.output is not None:
        args.output.write_text(rendered_output, encoding="utf-8")
    else:
        print(rendered_output)


if __name__ == "__main__":
    main()
