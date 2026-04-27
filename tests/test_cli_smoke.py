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


def test_main_help_smoke_lists_cli_taxonomy() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "CLI profesional" in result.stdout
    assert "metadata" in result.stdout
    assert "pipeline" in result.stdout
    assert "data-layout" in result.stdout
    assert "pre-ingestion" not in result.stdout
    assert "report" not in result.stdout


def test_metadata_group_help_smoke() -> None:
    result = run_cli("metadata", "--help")
    assert result.returncode == 0
    assert "explore" in result.stdout
    assert "from-doi" in result.stdout
    assert "seed-dois" in result.stdout
    assert "gap-seed-dois" not in result.stdout
    assert "export-csv" not in result.stdout


def test_metadata_explore_help_smoke() -> None:
    result = run_cli("metadata", "explore", "--help")
    assert result.returncode == 0
    assert "--mode" in result.stdout
    assert "broad-nutrition" in result.stdout
    assert "undercovered-topics" in result.stdout


def test_metadata_from_doi_help_smoke() -> None:
    result = run_cli("metadata", "from-doi", "--help")
    assert result.returncode == 0
    assert "--doi" in result.stdout
    assert "--overwrite" in result.stdout


def test_metadata_seed_dois_help_smoke() -> None:
    result = run_cli("metadata", "seed-dois", "--help")
    assert result.returncode == 0
    assert "--mode" in result.stdout
    assert "broad-nutrition" in result.stdout
    assert "undercovered-topics" in result.stdout
    assert "--metadata-dir" not in result.stdout
    assert "--topics-file" not in result.stdout


def test_bib_generate_help_smoke_mentions_optional_csv_source() -> None:
    result = run_cli("bib", "generate", "--help")
    assert result.returncode == 0
    assert "--input-csv" in result.stdout
    assert "missing_pdf_items.csv" in result.stdout


def test_pdfs_normalize_help_smoke_mentions_relations_csv() -> None:
    result = run_cli("pdfs", "normalize", "--help")
    assert result.returncode == 0
    assert "doi_pdf_relations" in result.stdout


def test_pipeline_help_smoke_lists_subcommands() -> None:
    result = run_cli("pipeline", "--help")
    assert result.returncode == 0
    assert "run" in result.stdout
    assert "single-paper" in result.stdout
    assert "run-all" not in result.stdout


def test_pipeline_single_paper_help_smoke() -> None:
    result = run_cli("pipeline", "single-paper", "--help")
    assert result.returncode == 0
    assert "--doi" in result.stdout
    assert "--max-claims" not in result.stdout
    assert "hasta claims" in result.stdout
    assert "data/archive/testing_1" in result.stdout


def test_pipeline_run_help_smoke_mentions_runners_flag() -> None:
    result = run_cli("pipeline", "run", "--help")
    assert result.returncode == 0
    assert "--runners" in result.stdout
    assert "--pdf" not in result.stdout


def test_claims_extract_help_smoke() -> None:
    result = run_cli("claims", "extract", "--help")
    assert result.returncode == 0
    assert "--max-claims" in result.stdout
    assert "--auto-approve-under-7000-tokens" in result.stdout
    assert "--skip-existing" in result.stdout


def test_data_layout_create_help_smoke() -> None:
    result = run_cli("data-layout", "create", "--help")
    assert result.returncode == 0
    assert "estructura canonica de directorios" in result.stdout


def test_main_prints_help_when_no_command(capsys) -> None:
    parser = cli.build_parser()
    parser.print_help()
    captured = capsys.readouterr()
    assert "metadata" in captured.out
    assert "claims" in captured.out


def test_main_routes_metadata_explore(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(sys, "argv", ["cli.py", "metadata", "explore", "--mode", "undercovered-topics"])
    monkeypatch.setattr(cli, "run_metadata_exploration_flow", lambda mode: called.append(mode))

    cli.main()

    assert called == ["undercovered-topics"]


def test_main_routes_metadata_seed_dois(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(sys, "argv", ["cli.py", "metadata", "seed-dois", "--mode", "undercovered-topics"])
    monkeypatch.setattr(cli, "_run_ops_script", lambda script_name, *args: called.append(script_name))

    cli.main()

    assert called == ["generate_metadata_gap_seed_dois.py"]


def test_main_routes_bib_generate(monkeypatch, tmp_path: Path) -> None:
    called: list[tuple[Path | None, Path | None]] = []
    output = tmp_path / "papers.bib"
    input_csv = tmp_path / "missing.csv"

    monkeypatch.setattr(
        sys,
        "argv",
        ["cli.py", "bib", "generate", "--output", str(output), "--input-csv", str(input_csv)],
    )
    monkeypatch.setattr(cli, "generate_bib_flow", lambda target, source_csv: called.append((target, source_csv)))

    cli.main()

    assert called == [(output.resolve(), input_csv.resolve())]


def test_main_routes_claims_extract(monkeypatch, tmp_path: Path) -> None:
    called: list[dict[str, object]] = []
    input_path = tmp_path / "input"
    output_path = tmp_path / "output"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cli.py",
            "claims",
            "extract",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--skip-existing",
            "--auto-approve-under-7000-tokens",
        ],
    )
    monkeypatch.setattr(cli, "run_llm_to_claim_flow", lambda **kwargs: called.append(kwargs))

    cli.main()

    assert called == [
        {
            "input_path": input_path,
            "output_path": output_path,
            "model": None,
            "max_claims": None,
            "temperature": None,
            "pattern": "*/*.final.json",
            "auto_approve_max_tokens": cli.ctx.LLM_CLAIMS_AUTO_APPROVE_MAX_TOKENS,
            "skip_existing": True,
        }
    ]


def test_main_routes_pipeline_run_with_runners(monkeypatch, tmp_path: Path) -> None:
    called: list[dict[str, object]] = []
    pdf_path = tmp_path / "paper.pdf"

    monkeypatch.setattr(
        sys,
        "argv",
        ["cli.py", "pipeline", "run", "--runners", "3", "--pdf", str(pdf_path)],
    )
    monkeypatch.setattr(cli, "run_pipeline_flow", lambda **kwargs: called.append(kwargs))

    cli.main()

    assert called == [
        {
            "runners": 3,
            "pdf_path": pdf_path.resolve(),
        }
    ]
