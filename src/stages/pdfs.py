from __future__ import annotations

from pathlib import Path

from src import config as ctx


def list_pdf_candidates() -> list[Path]:
    if not ctx.DOCLING_INPUT_DIR.exists():
        return []
    return sorted({p.resolve() for p in ctx.DOCLING_INPUT_DIR.glob("*.pdf")})


def sync_raw_pdfs() -> tuple[int, int]:
    sync_raw = ctx.resolve_raw_pdf_sync()
    return sync_raw(ctx.RAW_PDF_DIR, ctx.DOCLING_INPUT_DIR, ctx.METADATA_DIR, ctx.BIB_OUTPUT_FILE)


def normalize_pdfs_flow() -> None:
    ctx.ensure_dirs()
    copied_raw, skipped_raw = sync_raw_pdfs()

    print("Sincronizacion raw_pdf -> input_pdfs")
    print(f"- Copiados: {copied_raw}")
    print(f"- Omitidos: {skipped_raw}")
