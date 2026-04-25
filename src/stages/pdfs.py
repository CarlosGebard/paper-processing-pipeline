from __future__ import annotations

from pathlib import Path

from src import config as ctx
from src.tools.pdf_normalization import _default_relations_csv_from_metadata_dir, sync_raw_pdfs_from_relations


def list_pdf_candidates() -> list[Path]:
    if not ctx.DOCLING_INPUT_DIR.exists():
        return []
    return sorted({p.resolve() for p in ctx.DOCLING_INPUT_DIR.glob("*.pdf")})


def sync_raw_pdfs() -> tuple[int, int]:
    relations_csv = _default_relations_csv_from_metadata_dir(ctx.METADATA_DIR)
    if relations_csv is None:
        raise FileNotFoundError(
            "No se encontro doi_pdf_relations*.csv en data/analytics para normalizar PDFs desde relations."
        )
    raw_pdf_dir = ctx.resolve_available_raw_pdf_dir(ctx.RAW_PDF_DIR)
    return sync_raw_pdfs_from_relations(
        raw_pdf_dir,
        ctx.DOCLING_INPUT_DIR,
        relations_csv,
        unmatched_dir=ctx.UNMATCHED_PDF_DIR,
    )


def normalize_pdfs_flow() -> None:
    raw_pdf_dir = ctx.resolve_available_raw_pdf_dir(ctx.RAW_PDF_DIR)
    copied_raw, skipped_raw = sync_raw_pdfs()

    print("Sincronizacion raw_pdf -> normalized_pdfs via doi_pdf_relations.csv")
    if raw_pdf_dir != ctx.RAW_PDF_DIR:
        print(f"- raw_pdf_dir fallback: {ctx.display_path(raw_pdf_dir)}")
    print(f"- unmatched_pdf_dir: {ctx.display_path(ctx.UNMATCHED_PDF_DIR)}")
    print(f"- Copiados: {copied_raw}")
    print(f"- Omitidos: {skipped_raw}")
