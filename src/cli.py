from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from src import config as ctx
from .stages import (
    generate_bib_flow,
    normalize_pdfs_flow,
    run_llm_to_claim_flow,
    run_metadata_exploration_flow,
    run_pipeline_flow,
    run_single_paper_testing_flow,
)


CLI_DESCRIPTION = (
    "CLI profesional para el pipeline de papers. "
    "Organizada por dominios: metadata, bib, pdfs, pipeline, claims y data-layout."
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


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def _optional_resolved(path: Path | None) -> Path | None:
    return _resolved(path) if path is not None else None


def cmd_metadata_explore(args: argparse.Namespace) -> None:
    run_metadata_exploration_flow(mode=args.mode)


def cmd_metadata_from_doi(args: argparse.Namespace) -> None:
    script_args = [f"--doi={args.doi}"]
    if args.output_dir is not None:
        script_args.append(f"--output-dir={_resolved(args.output_dir)}")
    if args.overwrite:
        script_args.append("--overwrite")
    _run_ops_script("create_metadata_from_doi.py", *script_args)


def cmd_metadata_seed_dois(args: argparse.Namespace) -> None:
    if args.mode == "broad-nutrition":
        _run_ops_script("generate_metadata_seed_dois.py")
        return
    if args.mode == "undercovered-topics":
        _run_ops_script("generate_metadata_gap_seed_dois.py")
        return
    raise ValueError(f"Modo seed-dois no soportado: {args.mode}")


def cmd_bib_generate(args: argparse.Namespace) -> None:
    generate_bib_flow(
        _optional_resolved(args.output),
        _optional_resolved(args.input_csv),
    )


def cmd_pdfs_normalize(_args: argparse.Namespace) -> None:
    normalize_pdfs_flow()


def cmd_pipeline_run(_args: argparse.Namespace) -> None:
    run_pipeline_flow()


def cmd_pipeline_single_paper(args: argparse.Namespace) -> None:
    run_single_paper_testing_flow(
        doi=args.doi,
    )


def cmd_claims_extract(args: argparse.Namespace) -> None:
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


def cmd_data_layout_create(_args: argparse.Namespace) -> None:
    _run_ops_script("create_data_layout.py")


def _add_shared_claims_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Modelo (default config llm_to_claim.model: {ctx.LLM_CLAIMS_MODEL})",
    )
    parser.add_argument(
        "--max-claims",
        type=int,
        default=None,
        help="Fixed max claims override (default auto: base 10 + extras)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Temperature (default config llm_to_claim.temperature: {ctx.LLM_CLAIMS_TEMPERATURE})",
    )


def _add_metadata_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    metadata_parser = subparsers.add_parser(
        "metadata",
        help="Operaciones de metadata, exploracion y seeds",
        description=(
            "Grupo de metadata. Incluye exploracion de papers, alta puntual desde DOI "
            "y generacion de seed DOIs."
        ),
    )
    metadata_subparsers = metadata_parser.add_subparsers(dest="metadata_command")

    metadata_explore_parser = metadata_subparsers.add_parser(
        "explore",
        help="Explora candidatos y guarda metadata canónica",
        description=(
            "Explora candidatos desde seed DOIs y guarda metadata en "
            f"{ctx.display_path(ctx.METADATA_DIR)}."
        ),
    )
    metadata_explore_parser.add_argument(
        "--mode",
        choices=["broad-nutrition", "undercovered-topics"],
        default="broad-nutrition",
        help=(
            "Perfil de exploracion. "
            "broad-nutrition hace barrido amplio de nutricion; "
            "undercovered-topics prioriza temas subcubiertos. "
            "Ambos consumen la cola configurada en exploration.seed_doi_file."
        ),
    )
    metadata_explore_parser.set_defaults(handler=cmd_metadata_explore)

    metadata_from_doi_parser = metadata_subparsers.add_parser(
        "from-doi",
        help="Crea un metadata JSON canónico desde un DOI",
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
    metadata_from_doi_parser.set_defaults(handler=cmd_metadata_from_doi)

    metadata_seed_dois_parser = metadata_subparsers.add_parser(
        "seed-dois",
        help="Genera seed DOIs usando perfil broad-nutrition o undercovered-topics",
    )
    metadata_seed_dois_parser.add_argument(
        "--mode",
        choices=["broad-nutrition", "undercovered-topics"],
        default="broad-nutrition",
        help=(
            "Perfil de generacion de seeds. "
            "broad-nutrition usa metadata local + diccionario de keywords; "
            "undercovered-topics usa pre-ingestion + topics de gaps. "
            "Cada modo usa sus defaults configurados."
        ),
    )
    metadata_seed_dois_parser.set_defaults(handler=cmd_metadata_seed_dois)


def _add_bib_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    bib_parser = subparsers.add_parser(
        "bib",
        help="Operaciones de bibliografia",
        description="Genera bibliografia BibTeX desde metadata canonica o desde CSV auxiliar.",
    )
    bib_subparsers = bib_parser.add_subparsers(dest="bib_command")

    bib_generate_parser = bib_subparsers.add_parser(
        "generate",
        help="Genera un archivo .bib",
    )
    bib_generate_parser.add_argument("--output", type=Path, default=None, help="Ruta opcional del archivo .bib")
    bib_generate_parser.add_argument(
        "--input-csv",
        type=Path,
        default=None,
        help="CSV opcional como fuente, por ejemplo data/analytics/missing_pdf_items.csv",
    )
    bib_generate_parser.set_defaults(handler=cmd_bib_generate)


def _add_pdfs_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pdfs_parser = subparsers.add_parser(
        "pdfs",
        help="Operaciones sobre PDFs crudos y normalizados",
    )
    pdfs_subparsers = pdfs_parser.add_subparsers(dest="pdfs_command")

    pdfs_normalize_parser = pdfs_subparsers.add_parser(
        "normalize",
        help=(
            "Normaliza raw PDFs hacia nombres DOI-first usando doi_pdf_relations*.csv "
            f"({ctx.display_path(ctx.RAW_PDF_DIR)} -> {ctx.display_path(ctx.DOCLING_INPUT_DIR)})"
        ),
        description=(
            "Normaliza raw PDFs hacia nombres DOI-first usando doi_pdf_relations*.csv "
            f"({ctx.display_path(ctx.RAW_PDF_DIR)} -> {ctx.display_path(ctx.DOCLING_INPUT_DIR)})"
        ),
    )
    pdfs_normalize_parser.set_defaults(handler=cmd_pdfs_normalize)


def _add_pipeline_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Ejecucion de etapas del pipeline",
    )
    pipeline_subparsers = pipeline_parser.add_subparsers(dest="pipeline_command")

    pipeline_run_parser = pipeline_subparsers.add_parser(
        "run",
        help=f"Ejecuta docling + heuristics en {ctx.display_path(ctx.DOCLING_HEURISTICS_DIR)}",
    )
    pipeline_run_parser.set_defaults(handler=cmd_pipeline_run)

    pipeline_single_paper_parser = pipeline_subparsers.add_parser(
        "single-paper",
        help=(
            "Procesa un DOI de punta a punta hasta claims usando su PDF normalizado y escribe artifacts en "
            f"{ctx.display_path(ctx.TESTING_ROOT_DIR)}"
        ),
        description=(
            "Procesa un DOI de punta a punta hasta claims usando su PDF normalizado y escribe artifacts en "
            f"{ctx.display_path(ctx.TESTING_ROOT_DIR)}"
        ),
    )
    pipeline_single_paper_parser.add_argument("--doi", type=str, required=True, help="DOI del paper a procesar")
    pipeline_single_paper_parser.set_defaults(handler=cmd_pipeline_single_paper)


def _add_claims_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    claims_parser = subparsers.add_parser(
        "claims",
        help="Extraccion de claims desde *.final.json",
    )
    claims_subparsers = claims_parser.add_subparsers(dest="claims_command")

    claims_extract_parser = claims_subparsers.add_parser(
        "extract",
        help=(
            f"Extrae claims desde {ctx.display_path(ctx.CLAIMS_INPUT_DIR)} "
            f"hacia {ctx.display_path(ctx.CLAIMS_OUTPUT_DIR)}"
        ),
    )
    claims_extract_parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Archivo final JSON o directorio de entrada (default config llm_to_claim.input_dir)",
    )
    claims_extract_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Archivo/directorio de salida (default config llm_to_claim.output_dir)",
    )
    _add_shared_claims_args(claims_extract_parser)
    claims_extract_parser.add_argument(
        "--pattern",
        type=str,
        default="*/*.final.json",
        help="Glob pattern cuando --input es directorio",
    )
    claims_extract_parser.add_argument(
        "--auto-approve-under-7000-tokens",
        action="store_true",
        help=(
            "Procesa automaticamente solo archivos con estimated_input_tokens "
            f"menor a {ctx.LLM_CLAIMS_AUTO_APPROVE_MAX_TOKENS}"
        ),
    )
    claims_extract_parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Salta archivos cuyo *.claims.json de salida ya existe",
    )
    claims_extract_parser.set_defaults(handler=cmd_claims_extract)


def _add_data_layout_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    data_layout_parser = subparsers.add_parser(
        "data-layout",
        help="Bootstrap explícito del layout canonico de data/",
    )
    data_layout_subparsers = data_layout_parser.add_subparsers(dest="data_layout_command")

    data_layout_create_parser = data_layout_subparsers.add_parser(
        "create",
        help="Crea de forma explícita la estructura canonica de directorios bajo data/",
        description="Crea de forma explícita la estructura canonica de directorios bajo data/",
    )
    data_layout_create_parser.set_defaults(handler=cmd_data_layout_create)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=CLI_DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command")

    _add_metadata_group(subparsers)
    _add_bib_group(subparsers)
    _add_pdfs_group(subparsers)
    _add_pipeline_group(subparsers)
    _add_claims_group(subparsers)
    _add_data_layout_group(subparsers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return

    handler(args)
