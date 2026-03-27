from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "run_parallel_docling.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("run_parallel_docling", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("No se pudo cargar run_parallel_docling.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_determine_effective_workers_caps_by_available_memory(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "read_available_memory_bytes", lambda: 10 * 1024**3)

    workers, note = module.determine_effective_workers(4, 6.0)

    assert workers == 1
    assert note is not None
    assert "Ajustando workers de 4 a 1" in note


def test_determine_effective_workers_keeps_requested_when_memory_unknown(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "read_available_memory_bytes", lambda: None)

    workers, note = module.determine_effective_workers(3, 6.0)

    assert workers == 3
    assert note is None
