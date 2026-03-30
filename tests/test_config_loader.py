from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import src.config as config_loader
from src import artifacts

ctx = config_loader

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "create_data_layout.py"
SPEC = importlib.util.spec_from_file_location("create_data_layout", SCRIPT_PATH)
assert SPEC and SPEC.loader
DATA_LAYOUT_SCRIPT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DATA_LAYOUT_SCRIPT
SPEC.loader.exec_module(DATA_LAYOUT_SCRIPT)


def test_resolve_project_path_uses_root_for_relative_paths() -> None:
    resolved = config_loader.resolve_project_path("data/example", Path("/tmp/fallback"))
    assert resolved == config_loader.ROOT_DIR / "data/example"


def test_load_env_file_reads_simple_key_values(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'SEMANTIC_SCHOLAR_API_KEY="demo-key"\nOPENAI_API_KEY=test-openai\n',
        encoding="utf-8",
    )

    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config_loader.load_env_file(env_file)

    assert config_loader.os.environ["SEMANTIC_SCHOLAR_API_KEY"] == "demo-key"
    assert config_loader.os.environ["OPENAI_API_KEY"] == "test-openai"


def test_get_env_or_config_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "env-key")

    value = config_loader.get_env_or_config(
        "SEMANTIC_SCHOLAR_API_KEY",
        "api",
        "semantic_scholar_api_key",
        config={"api": {"semantic_scholar_api_key": "config-key"}},
    )

    assert value == "env-key"


def test_get_env_or_config_falls_back_to_config(monkeypatch) -> None:
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)

    value = config_loader.get_env_or_config(
        "SEMANTIC_SCHOLAR_API_KEY",
        "api",
        "semantic_scholar_api_key",
        config={"api": {"semantic_scholar_api_key": "config-key"}},
    )

    assert value == "config-key"


def test_get_pipeline_paths_defaults_claims_output_to_stage_04() -> None:
    paths = config_loader.get_pipeline_paths({})

    assert paths["claims_output_dir"] == config_loader.DATA_DIR / "stages" / "04_claims"


def test_get_testing_paths_defaults_to_data_testing() -> None:
    paths = config_loader.get_testing_paths({})

    assert paths["testing_root_dir"] == config_loader.DATA_DIR / "testing"
    assert paths["testing_docling_dir"] == config_loader.DATA_DIR / "testing" / "docling"
    assert paths["testing_claims_dir"] == config_loader.DATA_DIR / "testing" / "claims"


def test_pre_ingestion_defaults_live_under_data_csv() -> None:
    assert config_loader.PRE_INGESTION_DIR == config_loader.DATA_DIR / "csv" / "pre_ingestion_topics"
    assert config_loader.PRE_INGESTION_PAPERS_CSV == config_loader.PRE_INGESTION_DIR / "papers.csv"
    assert config_loader.PRE_INGESTION_CANDIDATE_TERMS_CSV == config_loader.PRE_INGESTION_DIR / "candidate_terms_top500.csv"
    assert config_loader.PRE_INGESTION_DRAFT_TOPICS_YAML == config_loader.PRE_INGESTION_DIR / "draft_topics.yaml"
    assert config_loader.PRE_INGESTION_AUDIT_DIR == config_loader.PRE_INGESTION_DIR / "audit"


def test_get_data_layout_dirs_includes_runtime_archive_and_pre_ingestion_csv() -> None:
    layout_dirs = config_loader.get_data_layout_dirs()

    assert config_loader.DATA_RUNTIME_DIR in layout_dirs
    assert config_loader.DATA_ARCHIVE_DIR in layout_dirs
    assert config_loader.PRE_INGESTION_DIR in layout_dirs
    assert config_loader.PRE_INGESTION_AUDIT_DIR in layout_dirs


def test_get_exploration_seed_doi_file_defaults_to_sources_seed_file() -> None:
    path = config_loader.get_exploration_seed_doi_file({})

    assert path == config_loader.DATA_DIR / "sources" / "seed_dois.txt"


def test_get_exploration_completed_seed_doi_file_defaults_to_sources_completed_seed_file() -> None:
    path = config_loader.get_exploration_completed_seed_doi_file({})

    assert path == config_loader.DATA_DIR / "sources" / "explored_seed_dois.txt"


def test_get_claims_auto_approve_max_tokens_defaults_to_7000() -> None:
    value = config_loader.get_claims_auto_approve_max_tokens({})

    assert value == 7000


def test_create_data_layout_script_uses_canonical_layout(monkeypatch) -> None:
    created: list[Path] = []
    expected = (
        Path("/tmp/data"),
        Path("/tmp/data/sources"),
        Path("/tmp/data/stages"),
    )

    monkeypatch.setattr(DATA_LAYOUT_SCRIPT.ctx, "get_data_layout_dirs", lambda: expected)

    def fake_mkdir(self: Path, parents: bool, exist_ok: bool) -> None:
        assert parents is True
        assert exist_ok is True
        created.append(self)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    result = DATA_LAYOUT_SCRIPT.create_data_layout()

    assert result == expected
    assert created == list(expected)


def test_artifact_stage_status_detects_completed_pipeline(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ctx, "METADATA_DIR", tmp_path / "metadata")
    monkeypatch.setattr(ctx, "DOCLING_INPUT_DIR", tmp_path / "input_pdfs")
    monkeypatch.setattr(ctx, "DOCLING_HEURISTICS_DIR", tmp_path / "docling_heuristics")
    monkeypatch.setattr(ctx, "CLAIMS_OUTPUT_DIR", tmp_path / "claims")

    paths = artifacts.artifact_paths_for_base_name("doi-10.1000-demo")
    for name, path in paths.items():
        if name == "docling_heuristics_dir":
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    status = artifacts.artifact_stage_status(paths)

    assert status["docling"] is True
    assert status["heuristics"] is True
    assert status["claims"] is True
    assert status["completed"] is True
