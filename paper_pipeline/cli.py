from __future__ import annotations

import argparse
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


def _run_menu_bib() -> None:
    output = input("Ruta .bib de salida (Enter para default): ").strip()
    target = Path(output).expanduser().resolve() if output else None
    try:
        generate_bib_flow(target)
    except Exception as exc:
        print(f"Error generando .bib: {exc}")


def _run_menu_claims() -> None:
    try:
        run_llm_to_claim_flow()
    except Exception as exc:
        print(f"Error en llm_to_claim: {exc}")


def interactive_menu() -> None:
    ctx.ensure_dirs()

    while True:
        print("\n=== Paper Processing CLI ===")
        print("1) Metadata Retrieval")
        print(f"2) Metadata to bib ({ctx.display_path(ctx.METADATA_DIR)} -> papers.bib)")
        print("3) raw pdf to normalized")
        print("4) docling + heuristics + llm_sections")
        print("5) llm_to_claim")
        print("6) Ejecutar flujo completo hasta claims")
        print("7) Salir")

        choice = input("Selecciona una opcion: ").strip()

        if choice == "1":
            try:
                run_metadata_exploration_flow()
            except Exception as exc:
                print(f"Error en metadata: {exc}")
            continue

        if choice == "2":
            _run_menu_bib()
            continue

        if choice == "3":
            normalize_pdfs_flow()
            continue

        if choice == "4":
            run_pipeline_flow()
            continue

        if choice == "5":
            _run_menu_claims()
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI unificada para metadata DOI -> Docling -> Heuristics"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("menu", help="Abre menu interactivo")
    subparsers.add_parser("metadata", help="1. Metadata Retrieval")

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
        help=f"Max claims (default config llm_to_claim.max_claims: {ctx.LLM_CLAIMS_MAX})",
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
        help="Archivo/directorio de entrada (default config llm_to_claim.input_dir)",
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
        help=f"Max claims (default config llm_to_claim.max_claims: {ctx.LLM_CLAIMS_MAX})",
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in (None, "menu"):
        interactive_menu()
        return

    if args.command == "metadata":
        run_metadata_exploration_flow()
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

    if args.command == "claims":
        run_llm_to_claim_flow(
            input_path=args.input,
            output_path=args.output,
            model=args.model,
            max_claims=args.max_claims,
            temperature=args.temperature,
            pattern=args.pattern,
        )
        return

    parser.print_help()
