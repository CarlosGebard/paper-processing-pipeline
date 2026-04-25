from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "analytics" / "reporting" / "export_pipeline_conversion_rates.py"
SPEC = importlib.util.spec_from_file_location("export_pipeline_conversion_rates", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_conversion_rows_computes_stage_rates(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "metadata"
    pdf_dir = tmp_path / "pdfs"
    docling_dir = tmp_path / "docling"
    claims_dir = tmp_path / "claims"
    metadata_dir.mkdir()
    pdf_dir.mkdir()
    docling_dir.mkdir()
    claims_dir.mkdir()

    for index in range(4):
        (metadata_dir / f"doi-10.1000-demo-{index}.metadata.json").write_text("{}", encoding="utf-8")
    for index in range(2):
        (pdf_dir / f"doi-10.1000-demo-{index}.pdf").write_text("", encoding="utf-8")
    for index in range(2):
        bundle = docling_dir / f"doi-10.1000-demo-{index}"
        bundle.mkdir()
        (bundle / f"doi-10.1000-demo-{index}.final.json").write_text("{}", encoding="utf-8")
    (claims_dir / "doi-10.1000-demo-0.claims.json").write_text("[]", encoding="utf-8")

    rows = MODULE.build_conversion_rows(
        metadata_dir=metadata_dir,
        pdf_dir=pdf_dir,
        docling_dir=docling_dir,
        claims_dir=claims_dir,
    )

    assert [row["stage"] for row in rows] == ["metadata", "pdf", "heuristics_final", "claims"]
    assert rows[0]["count"] == 4
    assert rows[1]["count"] == 2
    assert rows[1]["conversion_percent_from_previous"] == 50.0
    assert rows[2]["conversion_percent_from_metadata"] == 50.0
    assert rows[3]["conversion_percent_from_previous"] == 50.0
    assert rows[3]["conversion_percent_from_metadata"] == 25.0


def test_write_csv_exports_conversion_rows(tmp_path: Path) -> None:
    rows = [
        {
            "stage": "metadata",
            "count": 10,
            "previous_stage": "",
            "previous_count": 0,
            "conversion_rate_from_previous": 1.0,
            "conversion_percent_from_previous": 100.0,
            "conversion_rate_from_metadata": 1.0,
            "conversion_percent_from_metadata": 100.0,
        }
    ]
    output = tmp_path / "pipeline_conversion_rates.csv"
    MODULE.write_csv(rows, output)

    with output.open(encoding="utf-8", newline="") as handle:
        exported = list(csv.DictReader(handle))

    assert len(exported) == 1
    assert exported[0]["stage"] == "metadata"
    assert exported[0]["count"] == "10"
