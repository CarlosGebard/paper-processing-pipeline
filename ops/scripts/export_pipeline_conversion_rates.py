#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config_loader as ctx


def count_matching_files(directory: Path, pattern: str) -> int:
    if not directory.exists():
        return 0
    return sum(1 for path in directory.glob(pattern) if path.is_file())


def build_conversion_rows(
    *,
    metadata_dir: Path,
    pdf_dir: Path,
    docling_dir: Path,
    claims_dir: Path,
) -> list[dict[str, str | int | float]]:
    metadata_count = count_matching_files(metadata_dir, "*.metadata.json")
    pdf_count = count_matching_files(pdf_dir, "*.pdf")
    final_count = count_matching_files(docling_dir, "*/*.final.json")
    claims_count = count_matching_files(claims_dir, "*.claims.json")

    stages = [
        ("metadata", metadata_count),
        ("pdf", pdf_count),
        ("heuristics_final", final_count),
        ("claims", claims_count),
    ]

    rows: list[dict[str, str | int | float]] = []
    metadata_base = metadata_count if metadata_count > 0 else 0
    previous_count: int | None = None
    previous_stage: str | None = None
    for stage_name, count in stages:
        rate_from_previous = 1.0 if previous_count is None and count > 0 else 0.0
        if previous_count is not None:
            rate_from_previous = (count / previous_count) if previous_count > 0 else 0.0

        rate_from_metadata = (count / metadata_base) if metadata_base > 0 else 0.0
        rows.append(
            {
                "stage": stage_name,
                "count": count,
                "previous_stage": previous_stage or "",
                "previous_count": previous_count or 0,
                "conversion_rate_from_previous": round(rate_from_previous, 4),
                "conversion_percent_from_previous": round(rate_from_previous * 100, 2),
                "conversion_rate_from_metadata": round(rate_from_metadata, 4),
                "conversion_percent_from_metadata": round(rate_from_metadata * 100, 2),
            }
        )
        previous_stage = stage_name
        previous_count = count

    return rows


def write_csv(rows: list[dict[str, str | int | float]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stage",
        "count",
        "previous_stage",
        "previous_count",
        "conversion_rate_from_previous",
        "conversion_percent_from_previous",
        "conversion_rate_from_metadata",
        "conversion_percent_from_metadata",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, str | int | float]], output_path: Path) -> None:
    print("Pipeline conversion rates")
    print(f"- CSV: {ctx.display_path(output_path)}")
    for row in rows:
        print(
            f"- {row['stage']}: count={row['count']} | "
            f"from_previous={row['conversion_percent_from_previous']}% | "
            f"from_metadata={row['conversion_percent_from_metadata']}%"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export aggregate conversion rates across metadata, PDFs, final heuristics, and claims."
    )
    parser.add_argument("--metadata-dir", type=Path, default=ctx.METADATA_DIR)
    parser.add_argument("--pdf-dir", type=Path, default=ctx.DOCLING_INPUT_DIR)
    parser.add_argument("--docling-dir", type=Path, default=ctx.DOCLING_HEURISTICS_DIR)
    parser.add_argument("--claims-dir", type=Path, default=ctx.CLAIMS_OUTPUT_DIR)
    parser.add_argument("--output-csv", type=Path, default=ctx.DATA_DIR / "sources" / "pipeline_conversion_rates.csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_conversion_rows(
        metadata_dir=args.metadata_dir.expanduser().resolve(),
        pdf_dir=args.pdf_dir.expanduser().resolve(),
        docling_dir=args.docling_dir.expanduser().resolve(),
        claims_dir=args.claims_dir.expanduser().resolve(),
    )
    output_path = args.output_csv.expanduser().resolve()
    write_csv(rows, output_path)
    print_summary(rows, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
