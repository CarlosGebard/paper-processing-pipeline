#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def load_metadata_by_base_name(metadata_dir: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not metadata_dir.exists():
        return records

    for metadata_file in sorted(metadata_dir.glob("*.metadata.json")):
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        section = metadata_section(payload)
        if not isinstance(section, dict):
            continue
        records[metadata_file.name.removesuffix(".metadata.json")] = section

    return records


def _normalize_citations(value: Any) -> int | str:
    if value in (None, ""):
        return ""
    try:
        return int(value)
    except (TypeError, ValueError):
        return ""


def build_claim_rows(
    *,
    claims_dir: Path,
    metadata_dir: Path,
) -> list[dict[str, str | int]]:
    metadata_by_base = load_metadata_by_base_name(metadata_dir)
    rows: list[dict[str, str | int]] = []

    if not claims_dir.exists():
        return rows

    for claims_file in sorted(claims_dir.glob("*.claims.json")):
        base_name = claims_file.name.removesuffix(".claims.json")
        metadata = metadata_by_base.get(base_name, {})
        doi = str(metadata.get("doi") or "").strip()
        title_name = str(metadata.get("title") or "").strip()
        citations = _normalize_citations(metadata.get("citation_count", metadata.get("citationCount")))

        try:
            payload = json.loads(claims_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, list):
            continue

        for index, claim in enumerate(payload, start=1):
            if not isinstance(claim, dict):
                continue
            rows.append(
                {
                    "doi": doi,
                    "title_name": title_name,
                    "claim_number": index,
                    "citations": citations,
                }
            )

    return rows


def write_csv(rows: list[dict[str, str | int]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "title_name", "claim_number", "citations"])
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export one CSV row per claim using canonical metadata DOI, title, and citation count."
    )
    parser.add_argument("--claims-dir", type=Path, default=ctx.CLAIMS_OUTPUT_DIR)
    parser.add_argument("--metadata-dir", type=Path, default=ctx.METADATA_DIR)
    parser.add_argument("--output-csv", type=Path, default=ctx.CSV_DIR / "claims_export.csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_claim_rows(
        claims_dir=args.claims_dir.expanduser().resolve(),
        metadata_dir=args.metadata_dir.expanduser().resolve(),
    )
    output_path = args.output_csv.expanduser().resolve()
    write_csv(rows, output_path)
    print(f"CSV generado: {ctx.display_path(output_path)}")
    print(f"Filas exportadas: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
