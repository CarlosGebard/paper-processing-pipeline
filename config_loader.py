from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
CONFIG_FILE = ROOT_DIR / "config.yaml"
ENV_FILE = ROOT_DIR / ".env"


def resolve_project_path(path_value: str | None, fallback: Path) -> Path:
    if not path_value:
        return fallback
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def load_env_file(env_file: Path = ENV_FILE) -> None:
    if not env_file.exists() or not env_file.is_file():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


load_env_file()


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_pipeline_paths(config: dict[str, Any] | None = None) -> dict[str, Path]:
    cfg = config if config is not None else get_config()

    storage_cfg = cfg.get("storage") or {}
    docling_cfg = cfg.get("docling_ingestion") or {}
    llm_claims_cfg = cfg.get("llm_to_claim") or {}

    metadata_dir = resolve_project_path(
        storage_cfg.get("papers_dir"),
        DATA_DIR / "sources" / "metadata",
    )
    discarded_dir = resolve_project_path(
        storage_cfg.get("discarded_dir"),
        DATA_DIR / "sources" / "discarded_papers",
    )
    registry_dir = resolve_project_path(
        storage_cfg.get("registry_dir"),
        DATA_DIR / "sources" / "registry",
    )
    raw_pdf_dir = resolve_project_path(
        storage_cfg.get("raw_pdf_dir"),
        DATA_DIR / "stages" / "01_raw_pdf",
    )

    docling_input_dir = resolve_project_path(
        docling_cfg.get("input_dir"),
        DATA_DIR / "stages" / "02_input_pdfs",
    )
    docling_heuristics_dir = resolve_project_path(
        docling_cfg.get("output_dir"),
        DATA_DIR / "stages" / "03_docling_heuristics",
    )
    claims_input_dir = resolve_project_path(
        llm_claims_cfg.get("input_dir"),
        docling_heuristics_dir,
    )
    claims_output_dir = resolve_project_path(
        llm_claims_cfg.get("output_dir"),
        DATA_DIR / "stages" / "04_claims",
    )

    return {
        "metadata_dir": metadata_dir,
        "discarded_dir": discarded_dir,
        "registry_dir": registry_dir,
        "raw_pdf_dir": raw_pdf_dir,
        "docling_input_dir": docling_input_dir,
        "docling_heuristics_dir": docling_heuristics_dir,
        "claims_input_dir": claims_input_dir,
        "claims_output_dir": claims_output_dir,
    }


def get_env_or_config(
    env_name: str,
    *config_path: str,
    default: str | None = None,
    config: dict[str, Any] | None = None,
) -> str | None:
    env_value = os.getenv(env_name)
    if env_value:
        return env_value

    cfg = config if config is not None else get_config()
    current: Any = cfg
    for key in config_path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)

    if current in (None, ""):
        return default
    return str(current)


CONFIG = get_config()
PATHS = get_pipeline_paths(CONFIG)

METADATA_DIR = PATHS["metadata_dir"]
DOCLING_INPUT_DIR = PATHS["docling_input_dir"]
DOCLING_HEURISTICS_DIR = PATHS["docling_heuristics_dir"]
CLAIMS_INPUT_DIR = PATHS["claims_input_dir"]
CLAIMS_OUTPUT_DIR = PATHS["claims_output_dir"]
REGISTRY_DIR = PATHS["registry_dir"]
RAW_PDF_DIR = PATHS["raw_pdf_dir"]

LLM_CLAIMS_CFG = CONFIG.get("llm_to_claim") or {}
LLM_CLAIMS_MODEL = str(LLM_CLAIMS_CFG.get("model", "gpt-5-mini"))
LLM_CLAIMS_MAX = int(LLM_CLAIMS_CFG.get("max_claims", 10))
LLM_CLAIMS_TEMPERATURE = float(LLM_CLAIMS_CFG.get("temperature", 0.0))

REGISTRY_FILE = REGISTRY_DIR / "documents.jsonl"
BIB_OUTPUT_FILE = METADATA_DIR / "papers.bib"


def display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return str(resolved)


def ensure_dirs() -> None:
    required_dirs = (
        DATA_DIR,
        METADATA_DIR,
        DOCLING_INPUT_DIR,
        DOCLING_HEURISTICS_DIR,
        CLAIMS_OUTPUT_DIR,
        REGISTRY_DIR,
        RAW_PDF_DIR,
    )
    for directory in required_dirs:
        directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def resolve_docling_v2_pipeline_runner() -> Callable[..., dict[str, Any]]:
    from paper_pipeline.docling_pipeline.converter import convert_pdf_for_pipeline

    return convert_pdf_for_pipeline


@lru_cache(maxsize=1)
def resolve_raw_pdf_sync() -> Callable[[Path, Path, Path, Path | None], tuple[int, int]]:
    from paper_pipeline.tools.pdf_normalization import sync_raw_pdfs_into_input

    return sync_raw_pdfs_into_input


@lru_cache(maxsize=1)
def resolve_claims_flow() -> Callable[[Path, Path, str, int, float, str], tuple[int, int, int]]:
    from paper_pipeline.tools.claims_extraction import run_claim_extraction_flow

    return run_claim_extraction_flow
