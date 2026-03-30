from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import src.cli as cli


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "ops/scripts/cli.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_main_help_smoke() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "CLI unificada" in result.stdout
    assert "process-all" in result.stdout


def test_metadata_help_smoke() -> None:
    result = run_cli("metadata", "--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert "--mode" in result.stdout
    assert "nutrition-rag" in result.stdout


def test_metadata_from_doi_help_smoke() -> None:
    result = run_cli("metadata-from-doi", "--help")
    assert result.returncode == 0
    assert "--doi" in result.stdout
    assert "--overwrite" in result.stdout


def test_pre_ingestion_topics_help_smoke() -> None:
    result = run_cli("pre-ingestion-topics", "--help")
    assert result.returncode == 0
    assert "--input" in result.stdout
    assert "--topics" in result.stdout
    assert "--unmapped-min-doc-freq" in result.stdout


def test_draft_topics_from_citations_help_smoke() -> None:
    result = run_cli("draft-topics-from-citations", "--help")
    assert result.returncode == 0
    assert "--input" in result.stdout
    assert "--output-csv" in result.stdout
    assert "--output-yaml" in result.stdout
    assert "--min-doc-freq" in result.stdout


def test_claims_csv_help_smoke() -> None:
    result = run_cli("claims-csv", "--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert "claims-csv" in result.stdout


def test_claims_help_smoke() -> None:
    result = run_cli("claims", "--help")
    assert result.returncode == 0
    assert "--max-claims" in result.stdout
    assert "--auto-approve-under-7000-tokens" in result.stdout
    assert "--skip-existing" in result.stdout


def test_interactive_menu_routes_to_metadata_submenu(monkeypatch, capsys) -> None:
    called: list[str] = []
    answers = iter(["1", "5"])

    monkeypatch.setattr(cli.ctx, "ensure_dirs", lambda: None)
    monkeypatch.setattr(cli, "_run_menu_metadata", lambda: called.append("metadata"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    cli.interactive_menu()

    captured = capsys.readouterr()
    assert "=== Paper Processing CLI ===" in captured.out
    assert "Metadata Retrieval" in captured.out
    assert "llm_to_claim" in captured.out
    assert "Single-paper testing por DOI" not in captured.out
    assert called == ["metadata"]


def test_interactive_menu_routes_to_pipeline_and_scripts(monkeypatch, capsys) -> None:
    called: list[str] = []
    answers = iter(["2", "4", "5"])

    monkeypatch.setattr(cli.ctx, "ensure_dirs", lambda: None)
    monkeypatch.setattr(cli, "run_pipeline_flow", lambda: called.append("pipeline"))
    monkeypatch.setattr(cli, "interactive_scripts_menu", lambda: called.append("scripts-menu"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    cli.interactive_menu()

    captured = capsys.readouterr()
    assert "Scripts y utilidades" in captured.out
    assert called == ["pipeline", "scripts-menu"]


def test_metadata_submenu_routes_options(monkeypatch, capsys) -> None:
    called: list[str] = []
    answers = iter(["1", "2", "3", "4"])

    monkeypatch.setattr(cli, "run_metadata_exploration_flow", lambda mode: called.append(mode))
    monkeypatch.setattr(cli, "_run_menu_metadata_from_doi", lambda: called.append("metadata-from-doi"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    cli._run_menu_metadata()

    captured = capsys.readouterr()
    assert "Base file:" in captured.out
    assert "Automatico via LLM" in captured.out
    assert "Interactivo via CLI" in captured.out
    assert called == ["nutrition-rag", "interactive", "metadata-from-doi"]


def test_claims_submenu_routes_auto_and_single_paper(monkeypatch, capsys) -> None:
    called: list[str] = []
    answers = iter(["1", "2", "3"])

    monkeypatch.setattr(cli, "_run_menu_claims_auto", lambda: called.append("claims-auto"))
    monkeypatch.setattr(cli, "_run_menu_single_paper_testing", lambda: called.append("single-paper"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    cli._run_menu_claims_auto_only()

    captured = capsys.readouterr()
    assert "=== Claims ===" in captured.out
    assert "Ejecutar llm_to_claim automatico" in captured.out
    assert "Generar claims para un DOI" in captured.out
    assert called == ["claims-auto", "single-paper"]


def test_scripts_menu_routes_remaining_non_redundant_options(monkeypatch, capsys) -> None:
    called: list[str] = []
    answers = iter(["1", "2", "3", "7"])

    monkeypatch.setattr(cli.ctx, "ensure_dirs", lambda: None)
    monkeypatch.setattr(cli, "_run_menu_bib", lambda: called.append("bib"))
    monkeypatch.setattr(cli, "normalize_pdfs_flow", lambda: called.append("normalize-pdfs"))
    monkeypatch.setattr(cli, "_run_menu_metadata_citations_csv", lambda: called.append("metadata-citations-csv"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    cli.interactive_scripts_menu()

    captured = capsys.readouterr()
    assert "DOI to metadata" not in captured.out
    assert "Retrieve PDFs from metadata" not in captured.out
    assert "raw pdf to normalized" in captured.out
    assert "Metadata citations CSV" in captured.out
    assert called == ["bib", "normalize-pdfs", "metadata-citations-csv"]


def test_pre_ingestion_workspace_routes_canonical_steps(monkeypatch, capsys) -> None:
    called: list[str] = []
    answers = iter(["1", "2", "3", "4", "5"])

    monkeypatch.setattr(cli, "_run_menu_pre_ingestion_refresh_inputs", lambda: called.append("refresh"))
    monkeypatch.setattr(cli, "_run_menu_draft_topics_from_citations", lambda: called.append("draft"))
    monkeypatch.setattr(cli, "_run_menu_pre_ingestion_topics", lambda: called.append("audit"))
    monkeypatch.setattr(cli, "_run_menu_pre_ingestion_rebuild_all", lambda: called.append("rebuild"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    cli._run_menu_pre_ingestion_workspace()

    captured = capsys.readouterr()
    assert "=== Pre-ingestion Topics ===" in captured.out
    assert "Refrescar corpus base" in captured.out
    assert "Regenerar draft topic dictionary" in captured.out
    assert "Ejecutar topic audit" in captured.out
    assert "Rebuild completo desde corpus actual" in captured.out
    assert called == ["refresh", "draft", "audit", "rebuild"]


def test_pre_ingestion_audit_bootstraps_missing_inputs(monkeypatch, tmp_path, capsys) -> None:
    papers_csv = tmp_path / "pre_ingestion_topics" / "papers.csv"
    draft_topics = tmp_path / "pre_ingestion_topics" / "draft_topics.yaml"
    audit_dir = tmp_path / "pre_ingestion_topics" / "audit"
    called: list[str] = []

    monkeypatch.setattr(cli.ctx, "PRE_INGESTION_PAPERS_CSV", papers_csv)
    monkeypatch.setattr(cli.ctx, "PRE_INGESTION_DRAFT_TOPICS_YAML", draft_topics)
    monkeypatch.setattr(cli.ctx, "PRE_INGESTION_AUDIT_DIR", audit_dir)

    def fake_refresh() -> None:
        called.append("refresh")
        papers_csv.parent.mkdir(parents=True, exist_ok=True)
        papers_csv.write_text("paper_id,title\np1,Demo\n", encoding="utf-8")

    def fake_draft() -> None:
        called.append("draft")
        draft_topics.parent.mkdir(parents=True, exist_ok=True)
        draft_topics.write_text("topics:\n  demo:\n    keywords:\n      - demo\n", encoding="utf-8")

    monkeypatch.setattr(cli, "_run_menu_pre_ingestion_refresh_inputs", fake_refresh)
    monkeypatch.setattr(cli, "_run_menu_draft_topics_from_citations", fake_draft)
    monkeypatch.setattr(cli, "_run_ops_script", lambda script_name, *args: called.append(script_name))

    cli._run_menu_pre_ingestion_topics()

    captured = capsys.readouterr()
    assert "Falta papers.csv para el audit" in captured.out
    assert "Falta draft_topics.yaml para el audit" in captured.out
    assert called == ["refresh", "draft", "pre_ingestion_topic_audit.py"]


def test_single_paper_help_smoke() -> None:
    result = run_cli("single-paper", "--help")
    assert result.returncode == 0
    assert "--doi" in result.stdout
    assert "data/testing" in result.stdout
