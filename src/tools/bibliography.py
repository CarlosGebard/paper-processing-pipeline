#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from src import config as ctx
from src.config import get_config, get_pipeline_paths


CONFIG = get_config()
PATHS = get_pipeline_paths(CONFIG)
DEFAULT_INPUT_DIR = PATHS["metadata_dir"]
DEFAULT_OUTPUT_BIB = DEFAULT_INPUT_DIR / "papers.bib"


def sanitize_unicode(text: str) -> str:
    if not text:
        return ""

    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def latex_escape(text: str) -> str:
    replacements = {
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def clean_text(text: str) -> str:
    return latex_escape(sanitize_unicode(text))


def format_authors(authors: list[str]) -> str:
    return " and ".join(clean_text(author) for author in authors)


def generate_citekey(authors: list[str], year: Any, paper_id: str, used_keys: set[str]) -> str:
    if authors and year:
        last_name = re.sub(r"[^a-zA-Z0-9]", "", authors[0].split()[-1])
        key = f"{last_name}{year}"
    else:
        key = (paper_id or "paper")[:8]

    original = key
    counter = 1
    while key in used_keys:
        key = f"{original}{counter}"
        counter += 1

    used_keys.add(key)
    return key


def unwrap_record(raw: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw.get("metadata"), dict):
        return raw["metadata"]
    return raw


def json_to_bibtex_entry(data: dict[str, Any], used_keys: set[str]) -> str | None:
    doi = data.get("doi")
    if not doi:
        return None

    title = clean_text(str(data.get("title", "")))
    authors = [str(author) for author in (data.get("authors") or [])]
    year = data.get("year", "")
    paper_id = str(data.get("paperId") or data.get("document_id") or "")

    citekey = generate_citekey(authors, year, paper_id, used_keys)
    author_field = format_authors(authors)

    return (
        f"@article{{{citekey},\n"
        f"  title = {{{title}}},\n"
        f"  author = {{{author_field}}},\n"
        f"  year = {{{year}}},\n"
        f"  doi = {{{doi}}}\n"
        "}"
    )


def generate_bib(input_dir: Path, output_bib: Path) -> tuple[int, int]:
    used_keys: set[str] = set()
    entries: list[str] = []
    skipped = 0

    for json_file in sorted(input_dir.glob("*.json")):
        try:
            raw = json.loads(json_file.read_text(encoding="utf-8"))
            data = unwrap_record(raw)
            entry = json_to_bibtex_entry(data, used_keys)
            if entry:
                entries.append(entry)
            else:
                skipped += 1
        except Exception:
            skipped += 1

    output_bib.parent.mkdir(parents=True, exist_ok=True)
    output_bib.write_text("\n\n".join(entries), encoding="utf-8")
    return len(entries), skipped


def generate_bib_flow(output_file: Path | None = None) -> None:
    ctx.ensure_dirs()
    target = output_file or ctx.BIB_OUTPUT_FILE
    entries, skipped = generate_bib(ctx.METADATA_DIR, target)

    print("BibTeX generado")
    print(f"- Entradas: {entries}")
    print(f"- Omitidos: {skipped}")
    print(f"- Archivo:  {ctx.display_path(target)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convierte metadata JSON a BibTeX")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Carpeta con JSONs (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_BIB,
        help=f"Archivo .bib de salida (default: {DEFAULT_OUTPUT_BIB})",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    entries, skipped = generate_bib(args.input_dir, args.output)
    print(f"Generated {entries} BibTeX entries")
    print(f"Skipped {skipped} records")
    print(f"Output -> {args.output}")


if __name__ == "__main__":
    main()
