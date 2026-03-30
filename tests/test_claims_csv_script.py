from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "reporting" / "export_claims_csv.py"
SPEC = importlib.util.spec_from_file_location("export_claims_csv", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_claim_rows_joins_claims_with_metadata_and_numbers_rows(tmp_path: Path) -> None:
    claims_dir = tmp_path / "claims"
    metadata_dir = tmp_path / "metadata"
    claims_dir.mkdir()
    metadata_dir.mkdir()

    (claims_dir / "doi-10.1000-demo.claims.json").write_text(
        json.dumps([{"claim_text": "a"}, {"claim_text": "b"}]),
        encoding="utf-8",
    )
    (metadata_dir / "doi-10.1000-demo.metadata.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "doi": "10.1000/demo",
                    "title": "Example Paper",
                    "citation_count": 321,
                }
            }
        ),
        encoding="utf-8",
    )

    rows = MODULE.build_claim_rows(claims_dir=claims_dir, metadata_dir=metadata_dir)

    assert rows == [
        {
            "doi": "10.1000/demo",
            "title_name": "Example Paper",
            "claim_number": 1,
            "citations": 321,
        },
        {
            "doi": "10.1000/demo",
            "title_name": "Example Paper",
            "claim_number": 2,
            "citations": 321,
        },
    ]


def test_build_claim_rows_allows_missing_metadata_with_blank_fields(tmp_path: Path) -> None:
    claims_dir = tmp_path / "claims"
    metadata_dir = tmp_path / "metadata"
    claims_dir.mkdir()
    metadata_dir.mkdir()

    (claims_dir / "doi-10.1000-missing.claims.json").write_text(
        json.dumps([{"claim_text": "a"}]),
        encoding="utf-8",
    )

    rows = MODULE.build_claim_rows(claims_dir=claims_dir, metadata_dir=metadata_dir)

    assert rows == [
        {
            "doi": "",
            "title_name": "",
            "claim_number": 1,
            "citations": "",
        }
    ]


def test_write_csv_exports_claim_rows(tmp_path: Path) -> None:
    output = tmp_path / "claims_export.csv"
    rows = [
        {
            "doi": "10.1000/demo",
            "title_name": "Example Paper",
            "claim_number": 1,
            "citations": 321,
        }
    ]

    MODULE.write_csv(rows, output)

    with output.open(encoding="utf-8", newline="") as handle:
        exported = list(csv.DictReader(handle))

    assert exported == [
        {
            "doi": "10.1000/demo",
            "title_name": "Example Paper",
            "claim_number": "1",
            "citations": "321",
        }
    ]
