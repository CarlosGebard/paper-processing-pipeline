from __future__ import annotations

from pathlib import Path

import config_loader
from paper_pipeline import artifacts

ctx = config_loader


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
