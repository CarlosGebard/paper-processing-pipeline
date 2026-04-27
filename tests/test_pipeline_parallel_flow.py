from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src import config as ctx
from src.stages.processing import _run_pipeline_pdf_subprocess, run_pipeline_flow


def test_run_pipeline_pdf_subprocess_invokes_cli_with_single_pdf(monkeypatch, tmp_path: Path) -> None:
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    captured: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="ok output", stderr="")

    monkeypatch.setattr(ctx, "ROOT_DIR", root_dir)
    monkeypatch.setattr("src.stages.processing.subprocess.run", fake_run)

    name, ok, output = _run_pipeline_pdf_subprocess(pdf_path)

    assert name == "paper.pdf"
    assert ok is True
    assert output == "ok output"
    assert captured["cmd"] == [
        sys.executable,
        str(root_dir / "ops" / "scripts" / "cli.py"),
        "pipeline",
        "run",
        "--runners",
        "1",
        "--pdf",
        str(pdf_path),
    ]
    assert captured["kwargs"] == {
        "cwd": root_dir,
        "check": False,
        "capture_output": True,
        "text": True,
        "timeout": 1800,
    }


def test_run_pipeline_flow_queues_only_pending_pdfs(monkeypatch, capsys) -> None:
    pdfs = [
        Path("/tmp/complete.pdf"),
        Path("/tmp/heuristics.pdf"),
        Path("/tmp/pending-a.pdf"),
        Path("/tmp/pending-b.pdf"),
    ]
    registry = {
        "complete.pdf": {"stage_status": {"completed": True}},
        "heuristics.pdf": {"stage_status": {"heuristics": True}},
        "pending-a.pdf": {"stage_status": {}},
        "pending-b.pdf": {"stage_status": {}},
    }
    calls: list[Path] = []

    monkeypatch.setattr("src.stages.processing.list_pdf_candidates", lambda: pdfs)
    monkeypatch.setattr(
        "src.stages.processing.parse_document_from_pdf_name",
        lambda path: (path.stem.upper(), f"10.1000/{path.stem}", path.stem),
    )
    monkeypatch.setattr(
        "src.stages.processing.refresh_registry_record",
        lambda document_id, doi, base_name: registry[f"{base_name}.pdf"],
    )
    monkeypatch.setattr(
        "src.stages.processing._run_pipeline_pdf_subprocess",
        lambda pdf_path: calls.append(pdf_path) or (pdf_path.name, True, f"[OK] {pdf_path.name}"),
    )

    run_pipeline_flow(runners=2)

    assert calls == [Path("/tmp/pending-a.pdf"), Path("/tmp/pending-b.pdf")]
    captured = capsys.readouterr()
    assert "Pendientes: 2 PDFs" in captured.out
    assert "- Docling procesados:      2" in captured.out
    assert "- Heuristics procesados:   2" in captured.out
    assert "- Saltados completos:      1" in captured.out
    assert "- Saltados por heuristics: 1" in captured.out
    assert "- Fallidos:                0" in captured.out


def test_run_pipeline_flow_rejects_invalid_runners() -> None:
    with pytest.raises(ValueError, match="--runners debe ser >= 1"):
        run_pipeline_flow(runners=0)
