#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import config as ctx
from src.tools.pre_ingestion_topics import (
    audit_topics,
    build_summary,
    export_audit_artifacts,
    filter_papers_by_year,
    load_papers,
    load_topics_dictionary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audita cobertura tematica pre-ingestion usando solo titulos, "
            "sin LLMs ni embeddings."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Archivo de entrada CSV o JSONL con paper_id y title.",
    )
    parser.add_argument(
        "--topics",
        type=Path,
        required=True,
        help="Archivo YAML o JSON con topics canonicos y keywords.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ctx.PRE_INGESTION_AUDIT_DIR,
        help="Directorio donde se escriben los artifacts CSV/JSON.",
    )
    parser.add_argument("--min-year", type=int, default=None, help="Filtra papers con year >= este valor.")
    parser.add_argument("--max-year", type=int, default=None, help="Filtra papers con year <= este valor.")
    parser.add_argument(
        "--top-n-terms",
        type=int,
        default=10,
        help="Cantidad de terminos top a mostrar en el resumen por consola.",
    )
    parser.add_argument(
        "--top-n-topics",
        type=int,
        default=10,
        help="Cantidad de topics top a mostrar en el resumen por consola.",
    )
    parser.add_argument(
        "--unmapped-min-doc-freq",
        type=int,
        default=2,
        help="Doc frequency minima para exportar terminos frecuentes no mapeados.",
    )
    parser.add_argument(
        "--top-n-unmapped-terms",
        type=int,
        default=None,
        help="Limita la cantidad de terminos frecuentes no mapeados exportados.",
    )
    return parser.parse_args()


def print_summary(
    summary: dict[str, Any],
    *,
    output_dir: Path,
    top_n_topics: int,
    top_n_terms: int,
    top_n_unmapped_terms: int | None,
) -> None:
    print("Pre-ingestion thematic audit")
    print(f"- output_dir: {ctx.display_path(output_dir)}")
    print(f"- papers: {summary['paper_count']}")
    print(f"- classified: {summary['classified_paper_count']}")
    print(f"- unclassified: {summary['unclassified_paper_count']}")

    print(f"- top_topics (top {top_n_topics}):")
    top_topics = summary.get("top_topics") or []
    if top_topics:
        for row in top_topics:
            print(f"  - {row['topic']}: {row['paper_count']} papers ({row['relative_frequency']:.2%})")
    else:
        print("  - none")

    print(f"- top_terms (top {top_n_terms}):")
    top_terms = summary.get("top_terms") or []
    if top_terms:
        for row in top_terms:
            print(f"  - {row['term']}: doc_freq={row['doc_freq']}, total_freq={row['total_freq']}")
    else:
        print("  - none")

    unmapped_label = top_n_unmapped_terms if top_n_unmapped_terms is not None else top_n_terms
    print(f"- top_unmapped_terms (top {unmapped_label}):")
    top_unmapped_terms = summary.get("top_unmapped_terms") or []
    if top_unmapped_terms:
        for row in top_unmapped_terms:
            print(f"  - {row['term']}: doc_freq={row['doc_freq']}, total_freq={row['total_freq']}")
    else:
        print("  - none")


def main() -> int:
    args = parse_args()

    papers = load_papers(args.input.expanduser().resolve())
    topics = load_topics_dictionary(args.topics.expanduser().resolve())
    filtered_papers = filter_papers_by_year(
        papers,
        min_year=args.min_year,
        max_year=args.max_year,
    )
    audit = audit_topics(filtered_papers, topics)
    output_dir = args.output_dir.expanduser().resolve()
    export_audit_artifacts(
        audit,
        output_dir,
        unmapped_min_doc_freq=args.unmapped_min_doc_freq,
        top_n_unmapped_terms=args.top_n_unmapped_terms,
    )
    summary = build_summary(
        audit,
        top_n_terms=args.top_n_terms,
        top_n_topics=args.top_n_topics,
        unmapped_min_doc_freq=args.unmapped_min_doc_freq,
        top_n_unmapped_terms=args.top_n_unmapped_terms,
    )
    print_summary(
        summary,
        output_dir=output_dir,
        top_n_topics=args.top_n_topics,
        top_n_terms=args.top_n_terms,
        top_n_unmapped_terms=args.top_n_unmapped_terms,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
