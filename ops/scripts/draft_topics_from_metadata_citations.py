#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import config as ctx
from src.tools.pre_ingestion_topics import (
    build_draft_topics_yaml_payload,
    candidate_term_rows_to_csv,
    bootstrap_candidate_terms_from_citations,
    load_metadata_citations_as_papers,
    write_csv_rows,
    write_yaml,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera un CSV borrador de terminos candidatos para armar "
            "un topics.yaml a partir de metadata_citations.csv."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=ctx.CSV_DIR / "metadata_citations.csv",
        help="CSV de entrada con columnas title y citation_count.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ctx.PRE_INGESTION_CANDIDATE_TERMS_CSV,
        help="CSV de salida con terminos candidatos ponderados.",
    )
    parser.add_argument(
        "--output-yaml",
        type=Path,
        default=ctx.PRE_INGESTION_DRAFT_TOPICS_YAML,
        help="Ruta opcional para exportar un draft_topics.yaml curable.",
    )
    parser.add_argument("--min-doc-freq", type=int, default=2, help="Frecuencia minima por documento.")
    parser.add_argument("--min-n", type=int, default=2, help="N minimo del n-gram.")
    parser.add_argument("--max-n", type=int, default=3, help="N maximo del n-gram.")
    parser.add_argument("--top-n", type=int, default=500, help="Cantidad maxima de terminos exportados.")
    return parser.parse_args()


def print_summary(
    output_csv: Path,
    rows: list[dict[str, str | int | float]],
    *,
    output_yaml: Path | None,
    draft_topic_count: int,
) -> None:
    print("Topic bootstrap from metadata citations")
    print(f"- output_csv: {ctx.display_path(output_csv)}")
    if output_yaml is not None:
        print(f"- output_yaml: {ctx.display_path(output_yaml)}")
        print(f"- draft_topics: {draft_topic_count}")
    print(f"- exported_terms: {len(rows)}")
    for row in rows[:10]:
        print(
            f"  - {row['term']}: doc_freq={row['doc_freq']}, "
            f"citation_weight={row['citation_weight']}, score={row['combined_score']}"
        )


def main() -> int:
    args = parse_args()
    papers = load_metadata_citations_as_papers(args.input.expanduser().resolve())
    candidates = bootstrap_candidate_terms_from_citations(
        papers,
        min_n=args.min_n,
        max_n=args.max_n,
        min_doc_freq=args.min_doc_freq,
        top_n=args.top_n,
    )
    rows = candidate_term_rows_to_csv(candidates)
    output_csv = args.output_csv.expanduser().resolve()
    write_csv_rows(
        rows,
        output_csv,
        ["term", "n_tokens", "doc_freq", "total_freq", "citation_weight", "combined_score", "example_titles"],
    )
    output_yaml: Path | None = None
    draft_topic_count = 0
    if args.output_yaml is not None:
        output_yaml = args.output_yaml.expanduser().resolve()
        payload = build_draft_topics_yaml_payload(candidates)
        draft_topic_count = len(payload.get("topics") or {})
        write_yaml(payload, output_yaml)
    print_summary(output_csv, rows, output_yaml=output_yaml, draft_topic_count=draft_topic_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
