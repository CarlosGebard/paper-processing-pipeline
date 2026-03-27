from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import config_loader as ctx
from .stages import (
    generate_bib_flow,
    normalize_pdfs_flow,
    run_end_to_end_flow,
    run_llm_to_claim_flow,
    run_metadata_exploration_flow,
    run_pipeline_flow,
)

AUTO_APPROVE_CLAIMS_MAX_TOKENS = 7000


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
            auto_approve_max_tokens=AUTO_APPROVE_CLAIMS_MAX_TOKENS,
            skip_existing=True,
        )
    except Exception as exc:
        print(f"Error en llm_to_claim auto: {exc}")


def _run_menu_docling_stats() -> None:
    try:
        _run_ops_script("backfill_docling_titles_and_export_stats.py")
    except Exception as exc:
        print(f"Error en stats de pipeline: {exc}")


def _run_menu_metadata_citations_csv() -> None:
    try:
        _run_ops_script("export_metadata_citations_csv.py")
    except Exception as exc:
        print(f"Error exportando metadata citations CSV: {exc}")


def _run_menu_pipeline_conversion_rates() -> None:
    try:
        _run_ops_script("export_pipeline_conversion_rates.py")
    except Exception as exc:
        print(f"Error exportando conversion rates de pipeline: {exc}")


def interactive_menu() -> None:
    ctx.ensure_dirs()

    while True:
        print("\n=== Paper Processing CLI ===")
        print("1) Metadata Retrieval")
        print("2) Metadata Retrieval (nutrition-rag selector)")
        print("3) docling + heuristics + llm_sections")
        print("4) llm_to_claim")
        print(f"5) llm_to_claim auto (< {AUTO_APPROVE_CLAIMS_MAX_TOKENS} tokens)")
        print("6) Ejecutar flujo completo hasta claims")
        print("7) Salir")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            try:
                run_metadata_exploration_flow(mode="interactive")
            except Exception as exc:
                print(f"Error en metadata: {exc}")
            continue

        if choice == "2":
            try:
                run_metadata_exploration_flow(mode="nutrition-rag")
            except Exception as exc:
                print(f"Error en metadata nutrition-rag: {exc}")
            continue

        if choice == "3":
            run_pipeline_flow()
            continue

        if choice == "4":
            _run_menu_claims()
            continue

        if choice == "5":
            _run_menu_claims_auto()
            continue

        if choice == "6":
            try:
                run_end_to_end_flow()
            except Exception as exc:
                print(f"Error en process-all: {exc}")
            continue

        if choice in {"7", "q", "Q", "exit", "EXIT", "salir", "SALIR"}:
            print("Saliendo.")
            return

        print("Opcion invalida.")


def interactive_scripts_menu() -> None:
    ctx.ensure_dirs()

    while True:
        print("\n=== Paper Processing Scripts CLI ===")
        print(f"1) Metadata to bib ({ctx.display_path(ctx.METADATA_DIR)} -> papers.bib)")
        print("2) raw pdf to normalized")
        print("3) Docling titles + pipeline stats CSV")
        print("4) Metadata citations CSV")
        print("5) Pipeline conversion rates CSV")
        print("6) Salir")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            _run_menu_bib()
            continue

        if choice == "2":
            normalize_pdfs_flow()
            continue

        if choice == "3":
            _run_menu_docling_stats()
            continue

        if choice == "4":
            _run_menu_metadata_citations_csv()
            continue

        if choice == "5":
            _run_menu_pipeline_conversion_rates()
            continue

        if choice in {"6", "q", "Q", "exit", "EXIT", "salir", "SALIR"}:
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
        help="Modo de retrieval metadata (default: interactive)",
    )

    bib_parser = subparsers.add_parser(
        "bib",
        help=(
            "2. Metadata to bib "
            f"({ctx.display_path(ctx.METADATA_DIR)} -> papers.bib)"
        ),
    )
    bib_parser.add_argument("--output", type=Path, default=None, help="Ruta opcional del archivo .bib de salida")

    subparsers.add_parser(
        "normalize-pdfs",
        help=(
            "3. raw pdf to normalized "
            f"({ctx.display_path(ctx.RAW_PDF_DIR)} -> {ctx.display_path(ctx.DOCLING_INPUT_DIR)})"
        ),
    )

    subparsers.add_parser(
        "docling-stats",
        help="Backfill de paper_title en docling_heuristics y export de CSV final de stats",
    )

    subparsers.add_parser(
        "metadata-citations-csv",
        help="Exporta CSV con titulos y citation_count desde metadata canonica",
    )

    subparsers.add_parser(
        "pipeline-conversion-rates",
        help="Exporta CSV con conversion rates agregados entre metadata, pdf, heuristics final y claims",
    )

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
            f"menor a {AUTO_APPROVE_CLAIMS_MAX_TOKENS}"
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

    if args.command == "bib":
        target = args.output.expanduser().resolve() if args.output else None
        generate_bib_flow(target)
        return

    if args.command == "normalize-pdfs":
        normalize_pdfs_flow()
        return

    if args.command == "docling-stats":
        _run_ops_script("backfill_docling_titles_and_export_stats.py")
        return

    if args.command == "metadata-citations-csv":
        _run_ops_script("export_metadata_citations_csv.py")
        return

    if args.command == "pipeline-conversion-rates":
        _run_ops_script("export_pipeline_conversion_rates.py")
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
                AUTO_APPROVE_CLAIMS_MAX_TOKENS if args.auto_approve_under_7000_tokens else None
            ),
            skip_existing=args.skip_existing,
        )
        return

    parser.print_help()
