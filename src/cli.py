from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from src import config as ctx
from .stages import (
    generate_bib_flow,
    normalize_pdfs_flow,
    run_end_to_end_flow,
    run_llm_to_claim_flow,
    run_metadata_exploration_flow,
    run_pipeline_flow,
    run_single_paper_testing_flow,
)


def _run_ops_script(script_name: str, *args: str) -> None:
    script_path = ctx.ROOT_DIR / "ops" / "scripts" / script_name
    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=ctx.ROOT_DIR,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"El script {script_name} fallo con exit code {result.returncode}.")


def _run_menu_bib() -> None:
    output = input("Ruta .bib de salida (Enter para default): ").strip()
    target = Path(output).expanduser().resolve() if output else None
    try:
        generate_bib_flow(target)
    except Exception as exc:
        print(f"Error generando .bib: {exc}")


def _run_menu_metadata_from_doi() -> None:
    doi = input("DOI a guardar como metadata: ").strip()
    if not doi:
        print("No se ingreso DOI.")
        return
    overwrite = input("Sobrescribir si ya existe? (y/n): ").strip().lower() in {"y", "yes", "s", "si"}
    try:
        args = [f"--doi={doi}"]
        if overwrite:
            args.append("--overwrite")
        _run_ops_script("create_metadata_from_doi.py", *args)
    except Exception as exc:
        print(f"Error creando metadata desde DOI: {exc}")


def _run_menu_claims() -> None:
    def review_claims_input(file_path: Path, preview: dict[str, object], output_path: Path) -> bool:
        title = str(preview.get("title") or file_path.stem)
        section_count = int(preview.get("section_count") or 0)
        estimated_tokens = int(preview.get("estimated_input_tokens") or 0)
        review_phase = str(preview.get("review_phase") or "initial")
        output_exists = bool(preview.get("output_exists"))

        print("\n=== Claims Review ===")
        print(f"Fase:                {'final' if review_phase == 'final' else 'inicial'}")
        print(f"Titulo:              {title}")
        print(f"Archivo:             {file_path.name}")
        print(f"Output:              {output_path.name}")
        print(f"Ya procesado:        {'si' if output_exists else 'no'}")
        print(f"Secciones:           {section_count}")
        print(f"Input tokens aprox.: {estimated_tokens}")

        while True:
            if review_phase == "final":
                prompt = "Procesar este paper para claims ahora? (y/n): "
            else:
                prompt = "Procesar este paper para claims ahora? (y/n, n=standby): "
            decision = input(prompt).strip().lower()
            if decision in {"y", "yes", "s", "si"}:
                return True
            if decision in {"n", "no"}:
                return False
            print("Respuesta invalida. Usa y/n.")

    try:
        run_llm_to_claim_flow(review_callback=review_claims_input)
    except Exception as exc:
        print(f"Error en llm_to_claim: {exc}")


def _run_menu_claims_auto() -> None:
    try:
        run_llm_to_claim_flow(
            auto_approve_max_tokens=ctx.LLM_CLAIMS_AUTO_APPROVE_MAX_TOKENS,
            skip_existing=True,
        )
    except Exception as exc:
        print(f"Error en llm_to_claim auto: {exc}")


def _run_menu_metadata() -> None:
    while True:
        print("\n=== Metadata Retrieval ===")
        print(f"Base file: {ctx.display_path(ctx.EXPLORATION_SEED_DOI_FILE)}")
        print("1) Automatico via LLM")
        print("2) Interactivo via CLI")
        print("3) Single-paper metadata desde DOI")
        print("4) Volver")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            try:
                run_metadata_exploration_flow(mode="nutrition-rag")
            except Exception as exc:
                print(f"Error en metadata automatico: {exc}")
            continue

        if choice == "2":
            try:
                run_metadata_exploration_flow(mode="interactive")
            except Exception as exc:
                print(f"Error en metadata interactivo: {exc}")
            continue

        if choice == "3":
            _run_menu_metadata_from_doi()
            continue

        if choice in {"4", "q", "Q", "back", "volver", "VOLVER"}:
            return

        print("Opcion invalida.")


def _run_menu_claims_auto_only() -> None:
    while True:
        print("\n=== Claims ===")
        print(f"Input:  {ctx.display_path(ctx.CLAIMS_INPUT_DIR)}")
        print(f"Output: {ctx.display_path(ctx.CLAIMS_OUTPUT_DIR)}")
        print(f"Auto approve max tokens: {ctx.LLM_CLAIMS_AUTO_APPROVE_MAX_TOKENS}")
        print("1) Ejecutar llm_to_claim automatico")
        print(f"2) Generar claims para un DOI ({ctx.display_path(ctx.TESTING_ROOT_DIR)})")
        print("3) Volver")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            _run_menu_claims_auto()
            continue

        if choice == "2":
            _run_menu_single_paper_testing()
            continue

        if choice in {"3", "q", "Q", "back", "volver", "VOLVER"}:
            return

        print("Opcion invalida.")


def _run_menu_metadata_citations_csv() -> None:
    try:
        _run_ops_script("reporting/export_metadata_citations_csv.py")
    except Exception as exc:
        print(f"Error exportando metadata citations CSV: {exc}")


def _run_menu_pipeline_conversion_rates() -> None:
    try:
        _run_ops_script("reporting/export_pipeline_conversion_rates.py")
    except Exception as exc:
        print(f"Error exportando conversion rates de pipeline: {exc}")


def _run_menu_claims_csv() -> None:
    try:
        _run_ops_script("reporting/export_claims_csv.py")
    except Exception as exc:
        print(f"Error exportando claims CSV: {exc}")


def _run_menu_single_paper_testing() -> None:
    doi = input("DOI del paper a procesar en data/testing: ").strip()
    if not doi:
        print("No se ingreso DOI.")
        return
    try:
        run_single_paper_testing_flow(doi=doi)
    except Exception as exc:
        print(f"Error en single-paper testing: {exc}")


def _ensure_pre_ingestion_audit_inputs() -> bool:
    if not ctx.PRE_INGESTION_PAPERS_CSV.exists():
        print(
            "Falta papers.csv para el audit. "
            "Refrescando corpus base en data/csv/pre_ingestion_topics."
        )
        _run_menu_pre_ingestion_refresh_inputs()

    if not ctx.PRE_INGESTION_DRAFT_TOPICS_YAML.exists():
        print(
            "Falta draft_topics.yaml para el audit. "
            "Regenerando draft topic dictionary desde metadata_citations.csv."
        )
        _run_menu_draft_topics_from_citations()

    missing_paths = [
        path
        for path in (ctx.PRE_INGESTION_PAPERS_CSV, ctx.PRE_INGESTION_DRAFT_TOPICS_YAML)
        if not path.exists()
    ]
    if missing_paths:
        print("No fue posible preparar todos los inputs de pre-ingestion.")
        for path in missing_paths:
            print(f"- Missing: {ctx.display_path(path)}")
        return False
    return True


def _run_menu_pre_ingestion_topics() -> None:
    if not _ensure_pre_ingestion_audit_inputs():
        return
    try:
        _run_ops_script(
            "pre_ingestion_topic_audit.py",
            f"--input={ctx.PRE_INGESTION_PAPERS_CSV}",
            f"--topics={ctx.PRE_INGESTION_DRAFT_TOPICS_YAML}",
            f"--output-dir={ctx.PRE_INGESTION_AUDIT_DIR}",
        )
    except Exception as exc:
        print(f"Error en pre-ingestion topics: {exc}")


def _run_menu_draft_topics_from_citations() -> None:
    try:
        _run_ops_script(
            "draft_topics_from_metadata_citations.py",
            f"--input={ctx.CSV_DIR / 'metadata_citations.csv'}",
            f"--output-csv={ctx.PRE_INGESTION_CANDIDATE_TERMS_CSV}",
            f"--output-yaml={ctx.PRE_INGESTION_DRAFT_TOPICS_YAML}",
        )
    except Exception as exc:
        print(f"Error en draft topics from citations: {exc}")


def _run_menu_pre_ingestion_refresh_inputs() -> None:
    try:
        _run_ops_script("reporting/export_pre_ingestion_papers_csv.py")
        _run_ops_script("reporting/export_metadata_citations_csv.py")
    except Exception as exc:
        print(f"Error refrescando inputs de pre-ingestion: {exc}")


def _run_menu_pre_ingestion_rebuild_all() -> None:
    try:
        _run_ops_script("reporting/export_pre_ingestion_papers_csv.py")
        _run_ops_script("reporting/export_metadata_citations_csv.py")
        _run_menu_draft_topics_from_citations()
        _run_menu_pre_ingestion_topics()
    except Exception as exc:
        print(f"Error reconstruyendo workspace de pre-ingestion: {exc}")


def _run_menu_pre_ingestion_workspace() -> None:
    while True:
        print("\n=== Pre-ingestion Topics ===")
        print(f"Papers CSV:          {ctx.display_path(ctx.PRE_INGESTION_PAPERS_CSV)}")
        print(f"Metadata citations:  {ctx.display_path(ctx.CSV_DIR / 'metadata_citations.csv')}")
        print(f"Candidate terms:     {ctx.display_path(ctx.PRE_INGESTION_CANDIDATE_TERMS_CSV)}")
        print(f"Draft topics YAML:   {ctx.display_path(ctx.PRE_INGESTION_DRAFT_TOPICS_YAML)}")
        print(f"Audit output dir:    {ctx.display_path(ctx.PRE_INGESTION_AUDIT_DIR)}")
        print("1) Refrescar corpus base")
        print("2) Regenerar draft topic dictionary")
        print("3) Ejecutar topic audit")
        print("4) Rebuild completo desde corpus actual")
        print("5) Volver")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            _run_menu_pre_ingestion_refresh_inputs()
            continue

        if choice == "2":
            _run_menu_draft_topics_from_citations()
            continue

        if choice == "3":
            _run_menu_pre_ingestion_topics()
            continue

        if choice == "4":
            _run_menu_pre_ingestion_rebuild_all()
            continue

        if choice in {"5", "q", "Q", "back", "volver", "VOLVER"}:
            return

        print("Opcion invalida.")


def interactive_menu() -> None:
    ctx.ensure_dirs()

    while True:
        print("\n=== Paper Processing CLI ===")
        print("1) Metadata Retrieval")
        print("2) docling + heuristics + llm_sections")
        print("3) llm_to_claim")
        print("4) Scripts y utilidades")
        print("5) Salir")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            _run_menu_metadata()
            continue

        if choice == "2":
            run_pipeline_flow()
            continue

        if choice == "3":
            _run_menu_claims_auto_only()
            continue

        if choice == "4":
            interactive_scripts_menu()
            continue

        if choice in {"5", "q", "Q", "exit", "EXIT", "salir", "SALIR"}:
            print("Saliendo.")
            return

        print("Opcion invalida.")


def interactive_scripts_menu() -> None:
    ctx.ensure_dirs()

    while True:
        print("\n=== Paper Processing Scripts CLI ===")
        print(f"1) Metadata to bib ({ctx.display_path(ctx.METADATA_DIR)} -> papers.bib)")
        print(
            "2) raw pdf to normalized "
            f"({ctx.display_path(ctx.RAW_PDF_DIR)} -> {ctx.display_path(ctx.DOCLING_INPUT_DIR)})"
        )
        print("3) Metadata citations CSV")
        print("4) Pipeline conversion rates CSV")
        print("5) Claims CSV")
        print("6) Pre-ingestion topics workspace")
        print("7) Salir")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            _run_menu_bib()
            continue

        if choice == "2":
            normalize_pdfs_flow()
            continue

        if choice == "3":
            _run_menu_metadata_citations_csv()
            continue

        if choice == "4":
            _run_menu_pipeline_conversion_rates()
            continue

        if choice == "5":
            _run_menu_claims_csv()
            continue

        if choice == "6":
            _run_menu_pre_ingestion_workspace()
            continue

        if choice in {"7", "q", "Q", "exit", "EXIT", "salir", "SALIR"}:
            print("Saliendo.")
            return

        print("Opcion invalida.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI unificada para metadata DOI -> Docling -> Heuristics"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("menu", help="Abre menu interactivo")
    subparsers.add_parser("scripts-menu", help="Abre menu interactivo de scripts")
    metadata_parser = subparsers.add_parser("metadata", help="1. Metadata Retrieval")
    metadata_parser.add_argument(
        "--mode",
        choices=["interactive", "nutrition-rag"],
        default="interactive",
        help=(
            "Modo de retrieval metadata "
            "(nutrition-rag usa la lista editable configurada en exploration.seed_doi_file)"
        ),
    )

    bib_parser = subparsers.add_parser(
        "bib",
        help=(
            "2. Metadata to bib "
            f"({ctx.display_path(ctx.METADATA_DIR)} -> papers.bib)"
        ),
    )
    bib_parser.add_argument("--output", type=Path, default=None, help="Ruta opcional del archivo .bib de salida")

    metadata_from_doi_parser = subparsers.add_parser(
        "metadata-from-doi",
        help=f"Crea un *.metadata.json desde un DOI en {ctx.display_path(ctx.METADATA_DIR)}",
    )
    metadata_from_doi_parser.add_argument("--doi", type=str, required=True, help="DOI del paper")
    metadata_from_doi_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directorio opcional de salida metadata",
    )
    metadata_from_doi_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobrescribe el metadata si ya existe",
    )

    subparsers.add_parser(
        "normalize-pdfs",
        help=(
            "3. raw pdf to normalized "
            f"({ctx.display_path(ctx.RAW_PDF_DIR)} -> {ctx.display_path(ctx.DOCLING_INPUT_DIR)})"
        ),
    )

    subparsers.add_parser(
        "metadata-citations-csv",
        help="Exporta CSV con titulos y citation_count desde metadata canonica",
    )

    subparsers.add_parser(
        "pipeline-conversion-rates",
        help="Exporta CSV con conversion rates agregados entre metadata, pdf, heuristics final y claims",
    )

    subparsers.add_parser(
        "claims-csv",
        help="Exporta CSV con una fila por claim usando doi, title_name y citation_count del metadata",
    )

    pre_ingestion_parser = subparsers.add_parser(
        "pre-ingestion-topics",
        help="Audita cobertura tematica pre-ingestion usando solo titulos y un diccionario controlado",
    )
    pre_ingestion_parser.add_argument("--input", type=Path, required=True, help="Archivo CSV o JSONL con paper_id y title")
    pre_ingestion_parser.add_argument("--topics", type=Path, required=True, help="Archivo YAML o JSON de topics canonicos")
    pre_ingestion_parser.add_argument(
        "--output-dir",
        type=Path,
        default=ctx.PRE_INGESTION_AUDIT_DIR,
        help="Directorio output de artifacts CSV/JSON",
    )
    pre_ingestion_parser.add_argument("--min-year", type=int, default=None, help="Filtra papers con year >= este valor")
    pre_ingestion_parser.add_argument("--max-year", type=int, default=None, help="Filtra papers con year <= este valor")
    pre_ingestion_parser.add_argument("--top-n-terms", type=int, default=10, help="Top N terminos para resumen")
    pre_ingestion_parser.add_argument("--top-n-topics", type=int, default=10, help="Top N topics para resumen")
    pre_ingestion_parser.add_argument(
        "--unmapped-min-doc-freq",
        type=int,
        default=2,
        help="Doc frequency minima para exportar terminos no mapeados",
    )
    pre_ingestion_parser.add_argument(
        "--top-n-unmapped-terms",
        type=int,
        default=None,
        help="Limita la cantidad de terminos no mapeados exportados",
    )

    draft_topics_parser = subparsers.add_parser(
        "draft-topics-from-citations",
        help="Genera un CSV borrador de terminos candidatos a partir de metadata_citations.csv",
    )
    draft_topics_parser.add_argument(
        "--input",
        type=Path,
        default=ctx.CSV_DIR / "metadata_citations.csv",
        help="CSV de entrada con title y citation_count",
    )
    draft_topics_parser.add_argument(
        "--output-csv",
        type=Path,
        default=ctx.PRE_INGESTION_CANDIDATE_TERMS_CSV,
        help="CSV output de terminos candidatos",
    )
    draft_topics_parser.add_argument(
        "--output-yaml",
        type=Path,
        default=ctx.PRE_INGESTION_DRAFT_TOPICS_YAML,
        help="YAML draft opcional con topics agrupados heuristícamente",
    )
    draft_topics_parser.add_argument("--min-doc-freq", type=int, default=2, help="Frecuencia minima por documento")
    draft_topics_parser.add_argument("--min-n", type=int, default=2, help="N minimo del n-gram")
    draft_topics_parser.add_argument("--max-n", type=int, default=3, help="N maximo del n-gram")
    draft_topics_parser.add_argument("--top-n", type=int, default=500, help="Cantidad maxima de terminos exportados")

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help=(
            "4. docling + heuristics y deja salida combinada en "
            f"{ctx.display_path(ctx.DOCLING_HEURISTICS_DIR)}"
        ),
    )

    process_all_parser = subparsers.add_parser(
        "process-all",
        help="Ejecuta flujo completo input_pdfs -> claims usando *.final.json",
    )
    process_all_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Modelo (default config llm_to_claim.model: {ctx.LLM_CLAIMS_MODEL})",
    )
    process_all_parser.add_argument(
        "--max-claims",
        type=int,
        default=None,
        help="Fixed max claims override (default auto: base 10 + extras)",
    )
    process_all_parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Temperature (default config llm_to_claim.temperature: {ctx.LLM_CLAIMS_TEMPERATURE})",
    )

    single_paper_parser = subparsers.add_parser(
        "single-paper",
        help=(
            "Procesa un DOI usando su PDF normalizado y escribe Docling/claims en "
            f"{ctx.display_path(ctx.TESTING_ROOT_DIR)}"
        ),
        description=(
            "Procesa un DOI usando su PDF normalizado y escribe Docling/claims en "
            f"{ctx.display_path(ctx.TESTING_ROOT_DIR)}"
        ),
    )
    single_paper_parser.add_argument("--doi", type=str, required=True, help="DOI del paper a procesar")
    single_paper_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Modelo (default config llm_to_claim.model: {ctx.LLM_CLAIMS_MODEL})",
    )
    single_paper_parser.add_argument(
        "--max-claims",
        type=int,
        default=None,
        help="Fixed max claims override (default auto: base 10 + extras)",
    )
    single_paper_parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Temperature (default config llm_to_claim.temperature: {ctx.LLM_CLAIMS_TEMPERATURE})",
    )

    claims_parser = subparsers.add_parser(
        "claims",
        help=(
            f"5. llm_to_claim desde *.final.json "
            f"({ctx.display_path(ctx.CLAIMS_INPUT_DIR)} -> {ctx.display_path(ctx.CLAIMS_OUTPUT_DIR)})"
        ),
    )
    claims_parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Archivo final JSON o directorio de entrada (default config llm_to_claim.input_dir)",
    )
    claims_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Archivo/directorio de salida (default config llm_to_claim.output_dir)",
    )
    claims_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Modelo (default config llm_to_claim.model: {ctx.LLM_CLAIMS_MODEL})",
    )
    claims_parser.add_argument(
        "--max-claims",
        type=int,
        default=None,
        help="Fixed max claims override (default auto: base 10 + extras)",
    )
    claims_parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Temperature (default config llm_to_claim.temperature: {ctx.LLM_CLAIMS_TEMPERATURE})",
    )
    claims_parser.add_argument(
        "--pattern",
        type=str,
        default="*/*.final.json",
        help="Glob pattern cuando --input es directorio",
    )
    claims_parser.add_argument(
        "--auto-approve-under-7000-tokens",
        action="store_true",
        help=(
            "Procesa automaticamente solo archivos con estimated_input_tokens "
            f"menor a {ctx.LLM_CLAIMS_AUTO_APPROVE_MAX_TOKENS}"
        ),
    )
    claims_parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Salta archivos cuyo *.claims.json de salida ya existe",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in (None, "menu"):
        interactive_menu()
        return

    if args.command == "scripts-menu":
        interactive_scripts_menu()
        return

    if args.command == "metadata":
        run_metadata_exploration_flow(mode=args.mode)
        return

    if args.command == "pipeline":
        run_pipeline_flow()
        return

    if args.command == "process-all":
        run_end_to_end_flow(
            model=args.model,
            max_claims=args.max_claims,
            temperature=args.temperature,
        )
        return

    if args.command == "single-paper":
        run_single_paper_testing_flow(
            doi=args.doi,
            model=args.model,
            max_claims=args.max_claims,
            temperature=args.temperature,
        )
        return

    if args.command == "bib":
        target = args.output.expanduser().resolve() if args.output else None
        generate_bib_flow(target)
        return

    if args.command == "metadata-from-doi":
        script_args = [f"--doi={args.doi}"]
        if args.output_dir:
            script_args.append(f"--output-dir={args.output_dir.expanduser().resolve()}")
        if args.overwrite:
            script_args.append("--overwrite")
        _run_ops_script("create_metadata_from_doi.py", *script_args)
        return

    if args.command == "normalize-pdfs":
        normalize_pdfs_flow()
        return

    if args.command == "metadata-citations-csv":
        _run_ops_script("reporting/export_metadata_citations_csv.py")
        return

    if args.command == "pipeline-conversion-rates":
        _run_ops_script("reporting/export_pipeline_conversion_rates.py")
        return

    if args.command == "claims-csv":
        _run_ops_script("reporting/export_claims_csv.py")
        return

    if args.command == "pre-ingestion-topics":
        script_args = [
            f"--input={args.input.expanduser().resolve()}",
            f"--topics={args.topics.expanduser().resolve()}",
            f"--output-dir={args.output_dir.expanduser().resolve()}",
            f"--top-n-terms={args.top_n_terms}",
            f"--top-n-topics={args.top_n_topics}",
            f"--unmapped-min-doc-freq={args.unmapped_min_doc_freq}",
        ]
        if args.min_year is not None:
            script_args.append(f"--min-year={args.min_year}")
        if args.max_year is not None:
            script_args.append(f"--max-year={args.max_year}")
        if args.top_n_unmapped_terms is not None:
            script_args.append(f"--top-n-unmapped-terms={args.top_n_unmapped_terms}")
        _run_ops_script("pre_ingestion_topic_audit.py", *script_args)
        return

    if args.command == "draft-topics-from-citations":
        script_args = [
            f"--input={args.input.expanduser().resolve()}",
            f"--output-csv={args.output_csv.expanduser().resolve()}",
            f"--min-doc-freq={args.min_doc_freq}",
            f"--min-n={args.min_n}",
            f"--max-n={args.max_n}",
            f"--top-n={args.top_n}",
        ]
        if args.output_yaml is not None:
            script_args.append(f"--output-yaml={args.output_yaml.expanduser().resolve()}")
        _run_ops_script("draft_topics_from_metadata_citations.py", *script_args)
        return

    if args.command == "claims":
        run_llm_to_claim_flow(
            input_path=args.input,
            output_path=args.output,
            model=args.model,
            max_claims=args.max_claims,
            temperature=args.temperature,
            pattern=args.pattern,
            auto_approve_max_tokens=(
                ctx.LLM_CLAIMS_AUTO_APPROVE_MAX_TOKENS if args.auto_approve_under_7000_tokens else None
            ),
            skip_existing=args.skip_existing,
        )
        return

    parser.print_help()
