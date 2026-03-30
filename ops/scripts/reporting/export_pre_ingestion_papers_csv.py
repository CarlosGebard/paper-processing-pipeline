#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import config as ctx


def metadata_section(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    section = payload.get("metadata")
    if isinstance(section, dict):
        return section
    return payload


def read_metadata_rows(metadata_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for metadata_file in sorted(metadata_dir.glob("*.json")):
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        section = metadata_section(payload)
        if not section:
            continue

        title = str(section.get("title") or "").strip()
        if not title:
            continue

        paper_id = (
            str(section.get("document_id") or "").strip()
            or str(section.get("paperId") or "").strip()
            or metadata_file.stem
        )
        year = str(section.get("year") or "").strip()
        doi = str(section.get("doi") or "").strip()
        journal = str(section.get("journal") or section.get("venue") or "").strip()

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "year": year,
                "doi": doi,
                "journal": journal,
            }
        )

    rows.sort(key=lambda item: item["title"].lower())
    return rows


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["paper_id", "title", "year", "doi", "journal"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ctx.ensure_dirs()
    metadata_dir = ctx.METADATA_DIR
    output_path = ctx.PRE_INGESTION_PAPERS_CSV

    rows = read_metadata_rows(metadata_dir)
    write_csv(rows, output_path)

    print(f"CSV generado: {ctx.display_path(output_path)}")
    print(f"Filas exportadas: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
