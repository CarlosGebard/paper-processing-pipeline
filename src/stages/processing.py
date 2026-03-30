from __future__ import annotations

from pathlib import Path

from src import config as ctx
from ..artifacts import (
    artifact_paths_for_base_name,
    build_base_name,
    parse_document_from_pdf_name,
    refresh_registry_record,
)
from .pdfs import list_pdf_candidates


def resolve_pdf_for_doi(doi: str, input_dir: Path | None = None) -> Path:
    base_name = build_base_name(doi)
    resolved_input_dir = (input_dir or ctx.DOCLING_INPUT_DIR).expanduser().resolve()

    canonical_pdf = resolved_input_dir / f"{base_name}.pdf"
    if canonical_pdf.exists():
        return canonical_pdf

    legacy_matches = sorted(resolved_input_dir.glob(f"*__{base_name}.pdf"))
    if len(legacy_matches) == 1:
        return legacy_matches[0].resolve()
    if len(legacy_matches) > 1:
        raise RuntimeError(
            f"Se encontraron multiples PDFs legacy para {doi} en {ctx.display_path(resolved_input_dir)}."
        )

    raise FileNotFoundError(
        f"No existe PDF normalizado para {doi} en {ctx.display_path(resolved_input_dir)}."
    )


def run_pipeline_flow() -> None:
    ctx.ensure_dirs()

    pdfs = list_pdf_candidates()
    if not pdfs:
        print(f"No hay PDFs en {ctx.display_path(ctx.DOCLING_INPUT_DIR)}.")
        return

    processed_docling = 0
    processed_heuristics = 0
    skipped_complete = 0
    skipped_existing_heuristics = 0
    failed = 0

    for pdf_path in pdfs:
        try:
            document_id, doi, base_name = parse_document_from_pdf_name(pdf_path)
            record = refresh_registry_record(document_id, doi, base_name)
            stage_status = record.get("stage_status", {})

            if stage_status.get("completed"):
                print(f"[SKIP COMPLETE] {pdf_path.name}")
                skipped_complete += 1
                continue

            artifact_paths = artifact_paths_for_base_name(base_name)

            if stage_status.get("heuristics"):
                print(f"[SKIP HEURISTICS] {pdf_path.name}: ya existe salida heuristics")
                skipped_existing_heuristics += 1
                continue

            runner = ctx.resolve_docling_v2_pipeline_runner()
            result = runner(
                input_pdf=pdf_path,
                output_root_dir=ctx.DOCLING_HEURISTICS_DIR,
                metadata_dir=ctx.METADATA_DIR,
                dotenv_path=ctx.ROOT_DIR / ".env",
                document_id=document_id,
                doi=doi,
                base_name=base_name,
            )
            output_dir = Path(result["output_dir"])
            docling_json = Path(result["json_path"])
            filtered_json = Path(result["filtered_json_path"])
            final_json = Path(result["final_json_path"])
            processed_docling += 1
            refresh_registry_record(document_id, doi, base_name)
            print(f"[OK] {pdf_path.name}")
            print(f"  - Output dir:    {ctx.display_path(output_dir)}")
            print(f"  - Docling JSON:  {ctx.display_path(docling_json)}")
            print(f"  - Filtered JSON: {ctx.display_path(filtered_json)}")
            print(f"  - Final JSON:    {ctx.display_path(final_json)}")
            processed_heuristics += 1
        except Exception as exc:
            print(f"[SKIP] {pdf_path.name}: {exc}")
            failed += 1

    print("\nResumen pipeline")
    print(f"- Docling procesados:      {processed_docling}")
    print(f"- Heuristics procesados:   {processed_heuristics}")
    print(f"- Saltados completos:      {skipped_complete}")
    print(f"- Saltados por heuristics: {skipped_existing_heuristics}")
    print(f"- Fallidos:                {failed}")


def run_end_to_end_flow(
    model: str | None = None,
    max_claims: int | None = None,
    temperature: float | None = None,
) -> None:
    ctx.ensure_dirs()

    pdfs = list_pdf_candidates()
    if not pdfs:
        print(f"No hay PDFs en {ctx.display_path(ctx.DOCLING_INPUT_DIR)}.")
        return

    chosen_model = model or ctx.LLM_CLAIMS_MODEL
    chosen_temp = temperature if temperature is not None else ctx.LLM_CLAIMS_TEMPERATURE

    docling_processed = 0
    heuristics_processed = 0
    claims_processed = 0
    claims_overwritten = 0
    skipped_docling_complete = 0
    failed = 0
    pending_claim_inputs: list[tuple[str, str, str, Path]] = []

    for pdf_path in pdfs:
        try:
            document_id, doi, base_name = parse_document_from_pdf_name(pdf_path)
            record = refresh_registry_record(document_id, doi, base_name)
            stage_status = record.get("stage_status", {})

            if not stage_status.get("heuristics"):
                runner = ctx.resolve_docling_v2_pipeline_runner()
                runner(
                    input_pdf=pdf_path,
                    output_root_dir=ctx.DOCLING_HEURISTICS_DIR,
                    metadata_dir=ctx.METADATA_DIR,
                    dotenv_path=ctx.ROOT_DIR / ".env",
                    document_id=document_id,
                    doi=doi,
                    base_name=base_name,
                )
                docling_processed += 1
                heuristics_processed += 1
            else:
                skipped_docling_complete += 1

            refreshed = refresh_registry_record(document_id, doi, base_name)
            final_json = Path(refreshed["paths"]["final_json"])
            final_stage_status = refreshed.get("stage_status", {})

            if final_stage_status.get("claims"):
                print(f"[OVERWRITE CLAIMS] {pdf_path.name}: ya existe salida claims, se regenerara")

            pending_claim_inputs.append((document_id, doi, base_name, final_json))
        except Exception as exc:
            print(f"[SKIP] {pdf_path.name}: {exc}")
            failed += 1

    for document_id, doi, base_name, final_json in pending_claim_inputs:
        try:
            claims_flow = ctx.resolve_claims_flow()
            processed, overwritten, claim_failures = claims_flow(
                final_json,
                ctx.CLAIMS_OUTPUT_DIR,
                chosen_model,
                max_claims,
                chosen_temp,
                "*/*.final.json",
            )
            claims_processed += processed
            claims_overwritten += overwritten
            failed += claim_failures
            refresh_registry_record(document_id, doi, base_name)
        except Exception as exc:
            print(f"[SKIP CLAIMS] {final_json.name}: {exc}")
            failed += 1

    print("\nResumen process-all")
    print(f"- Docling procesados:    {docling_processed}")
    print(f"- Heuristics procesados: {heuristics_processed}")
    print(f"- Claims procesados:     {claims_processed}")
    print(f"- Claims overwrite:      {claims_overwritten}")
    print(f"- Docling reutilizado:   {skipped_docling_complete}")
    print(f"- Fallidos:              {failed}")


def run_single_paper_testing_flow(
    doi: str,
    model: str | None = None,
    max_claims: int | None = None,
    temperature: float | None = None,
) -> dict[str, object]:
    ctx.ensure_dirs()

    pdf_path = resolve_pdf_for_doi(doi)
    document_id, resolved_doi, base_name = parse_document_from_pdf_name(pdf_path)

    runner = ctx.resolve_docling_v2_pipeline_runner()
    result = runner(
        input_pdf=pdf_path,
        output_root_dir=ctx.TESTING_DOCLING_DIR,
        metadata_dir=ctx.METADATA_DIR,
        dotenv_path=ctx.ROOT_DIR / ".env",
        document_id=document_id,
        doi=resolved_doi,
        base_name=base_name,
    )

    final_json = Path(result["final_json_path"])
    claims_flow = ctx.resolve_claims_flow()
    chosen_model = model or ctx.LLM_CLAIMS_MODEL
    chosen_temp = temperature if temperature is not None else ctx.LLM_CLAIMS_TEMPERATURE
    processed, overwritten, failed = claims_flow(
        final_json,
        ctx.TESTING_CLAIMS_DIR,
        chosen_model,
        max_claims,
        chosen_temp,
        "*/*.final.json",
    )
    claims_path = ctx.TESTING_CLAIMS_DIR / f"{base_name}.claims.json"

    print("\nResumen single-paper testing")
    print(f"- DOI:         {resolved_doi}")
    print(f"- PDF:         {ctx.display_path(pdf_path)}")
    print(f"- Docling dir: {ctx.display_path(Path(result['output_dir']))}")
    print(f"- Final JSON:  {ctx.display_path(final_json)}")
    print(f"- Claims:      {ctx.display_path(claims_path)}")
    print(f"- Processed:   {processed}")
    print(f"- Overwrite:   {overwritten}")
    print(f"- Failed:      {failed}")

    return {
        "doi": resolved_doi,
        "pdf_path": pdf_path,
        "docling_output_dir": Path(result["output_dir"]),
        "final_json_path": final_json,
        "claims_path": claims_path,
        "claims_processed": processed,
        "claims_overwritten": overwritten,
        "claims_failed": failed,
    }
