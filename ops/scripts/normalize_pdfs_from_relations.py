#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import config as ctx
from src.tools.pdf_normalization import _default_relations_csv_from_metadata_dir, sync_raw_pdfs_from_relations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normaliza PDFs crudos usando doi_pdf_relations*.csv como fuente de verdad para el renombrado DOI-first."
    )
    parser.add_argument("--raw-dir", type=Path, default=ctx.RAW_PDF_DIR, help="Directorio fuente de PDFs crudos.")
    parser.add_argument("--input-dir", type=Path, default=ctx.DOCLING_INPUT_DIR, help="Directorio destino normalizado.")
    parser.add_argument(
        "--unmatched-dir",
        type=Path,
        default=ctx.UNMATCHED_PDF_DIR,
        help="Directorio destino para PDFs que no logran mapearse a DOI.",
    )
    parser.add_argument(
        "--relations-csv",
        type=Path,
        default=None,
        help="CSV doi_pdf_relations explicito. Si no se indica, usa el ultimo encontrado en data/analytics.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    relations_csv = (
        args.relations_csv.expanduser().resolve()
        if args.relations_csv
        else _default_relations_csv_from_metadata_dir(ctx.METADATA_DIR)
    )
    if relations_csv is None:
        raise FileNotFoundError("No se encontro doi_pdf_relations*.csv en data/analytics.")
    raw_pdf_dir = (
        args.raw_dir.expanduser().resolve() if args.raw_dir != ctx.RAW_PDF_DIR else ctx.resolve_available_raw_pdf_dir(ctx.RAW_PDF_DIR)
    )

    copied, skipped = sync_raw_pdfs_from_relations(
        raw_pdf_dir=raw_pdf_dir,
        input_dir=args.input_dir.expanduser().resolve(),
        relations_csv=relations_csv,
        unmatched_dir=args.unmatched_dir.expanduser().resolve(),
    )

    print("Sincronizacion raw_pdf -> normalized_pdfs via doi_pdf_relations.csv")
    print(f"- relations_csv: {ctx.display_path(relations_csv)}")
    if raw_pdf_dir != ctx.RAW_PDF_DIR:
        print(f"- raw_pdf_dir fallback: {ctx.display_path(raw_pdf_dir)}")
    print(f"- unmatched_pdf_dir: {ctx.display_path(args.unmatched_dir.expanduser().resolve())}")
    print(f"- Copiados: {copied}")
    print(f"- Omitidos: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
