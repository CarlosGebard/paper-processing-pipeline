from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

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
    heuristics_cfg = cfg.get("heuristics") or {}
    llm_claims_cfg = cfg.get("llm_to_claim") or {}

    metadata_dir = resolve_project_path(
        storage_cfg.get("papers_dir"),
        DATA_DIR / "metadata",
    )
    discarded_dir = resolve_project_path(
        storage_cfg.get("discarded_dir"),
        DATA_DIR / "discarded_papers",
    )
    registry_dir = resolve_project_path(
        storage_cfg.get("registry_dir"),
        DATA_DIR / "registry",
    )
    raw_pdf_dir = resolve_project_path(
        storage_cfg.get("raw_pdf_dir"),
        DATA_DIR / "raw_pdf",
    )

    docling_input_dir = resolve_project_path(
        docling_cfg.get("input_dir"),
        DATA_DIR / "input_pdfs",
    )
    docling_output_dir = resolve_project_path(
        docling_cfg.get("output_dir"),
        ROOT_DIR / "output",
    )
    docling_json_dir = resolve_project_path(
        docling_cfg.get("json_dir"),
        DATA_DIR / "docling_extraction" / "json",
    )
    docling_markdown_dir = resolve_project_path(
        docling_cfg.get("markdown_dir"),
        DATA_DIR / "docling_extraction" / "markdown",
    )

    heuristics_full_dir = resolve_project_path(
        heuristics_cfg.get("full_dir"),
        DATA_DIR / "post_heuristics" / "full_doc",
    )
    heuristics_final_dir = resolve_project_path(
        heuristics_cfg.get("final_dir"),
        DATA_DIR / "post_heuristics" / "final",
    )
    claims_input_dir = resolve_project_path(
        llm_claims_cfg.get("input_dir"),
        heuristics_final_dir,
    )
    claims_output_dir = resolve_project_path(
        llm_claims_cfg.get("output_dir"),
        DATA_DIR / "claims",
    )

    return {
        "metadata_dir": metadata_dir,
        "discarded_dir": discarded_dir,
        "registry_dir": registry_dir,
        "raw_pdf_dir": raw_pdf_dir,
        "docling_input_dir": docling_input_dir,
        "docling_output_dir": docling_output_dir,
        "docling_json_dir": docling_json_dir,
        "docling_markdown_dir": docling_markdown_dir,
        "heuristics_full_dir": heuristics_full_dir,
        "heuristics_final_dir": heuristics_final_dir,
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
