from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_main_help_smoke() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "CLI unificada" in result.stdout


def test_metadata_help_smoke() -> None:
    result = run_cli("metadata", "--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_claims_help_smoke() -> None:
    result = run_cli("claims", "--help")
    assert result.returncode == 0
    assert "--max-claims" in result.stdout
