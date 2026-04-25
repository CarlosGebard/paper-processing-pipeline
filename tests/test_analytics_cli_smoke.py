from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import analytics.cli as analytics_cli


ROOT = Path(__file__).resolve().parents[1]


def run_analytics_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "analytics/cli.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_main_help_smoke_lists_analytics_taxonomy() -> None:
    result = run_analytics_cli("--help")
    assert result.returncode == 0
    assert "CLI de analytics" in result.stdout
    assert "metadata" in result.stdout
    assert "pre-ingestion" in result.stdout
    assert "report" in result.stdout


def test_metadata_group_help_smoke() -> None:
    result = run_analytics_cli("metadata", "--help")
    assert result.returncode == 0
    assert "export-csv" in result.stdout


def test_pre_ingestion_help_smoke_lists_subcommands() -> None:
    result = run_analytics_cli("pre-ingestion", "--help")
    assert result.returncode == 0
    assert "refresh-inputs" in result.stdout
    assert "draft-topics" in result.stdout
    assert "audit" in result.stdout
    assert "rebuild" in result.stdout


def test_pre_ingestion_audit_help_smoke() -> None:
    result = run_analytics_cli("pre-ingestion", "audit", "--help")
    assert result.returncode == 0
    assert "--input" in result.stdout
    assert "--topics" in result.stdout
    assert "--unmapped-min-doc-freq" in result.stdout


def test_report_conversion_rates_help_smoke() -> None:
    result = run_analytics_cli("report", "conversion-rates", "--help")
    assert result.returncode == 0
    assert "conversion-rates" in result.stdout


def test_main_routes_pre_ingestion_refresh_inputs(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(sys, "argv", ["cli.py", "pre-ingestion", "refresh-inputs"])
    monkeypatch.setattr(analytics_cli, "_run_analytics_script", lambda script_name, *args: called.append(script_name))

    analytics_cli.main()

    assert called == [
        "reporting/export_pre_ingestion_papers_csv.py",
        "reporting/export_metadata_citations_csv.py",
    ]
