from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "analytics" / "reporting" / "export_metadata_citations_csv.py"
SPEC = importlib.util.spec_from_file_location("export_metadata_csv", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_read_metadata_rows_includes_doi_and_sorts_by_citations(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    (metadata_dir / "b.metadata.json").write_text(
        json.dumps({"metadata": {"doi": "10.1000/low", "title": "Lower paper", "citationCount": 3}}),
        encoding="utf-8",
    )
    (metadata_dir / "a.metadata.json").write_text(
        json.dumps({"metadata": {"doi": "10.1000/high", "title": "Higher paper", "citationCount": 9}}),
        encoding="utf-8",
    )

    rows = MODULE.read_metadata_rows(metadata_dir)

    assert rows == [
        {"doi": "10.1000/high", "title": "Higher paper", "citation_count": 9},
        {"doi": "10.1000/low", "title": "Lower paper", "citation_count": 3},
    ]


def test_write_csv_exports_metadata_rows_with_doi(tmp_path: Path) -> None:
    output = tmp_path / "metadata.csv"
    rows = [{"doi": "10.1000/demo", "title": "Example Paper", "citation_count": 321}]

    MODULE.write_csv(rows, output)

    with output.open(encoding="utf-8", newline="") as handle:
        exported = list(csv.DictReader(handle))

    assert exported == [
        {
            "doi": "10.1000/demo",
            "title": "Example Paper",
            "citation_count": "321",
        }
    ]
