from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "ops"
    / "scripts"
    / "backfill_docling_titles_and_export_stats.py"
)
SPEC = importlib.util.spec_from_file_location("backfill_docling_titles_and_export_stats", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_backfill_docling_titles_updates_filtered_and_final(tmp_path: Path, monkeypatch) -> None:
    docling_dir = tmp_path / "03_docling_heuristics" / "doi-10.1000-demo"
    docling_dir.mkdir(parents=True)
    filtered_path = docling_dir / "doi-10.1000-demo.filtered.json"
    final_path = docling_dir / "doi-10.1000-demo.final.json"

    filtered_path.write_text(
        json.dumps(
            {
                "schema_name": "FilteredCleanDoclingDocument",
                "paper_title": "None",
                "source": {"name": "doi-10.1000-demo"},
                "sections": [],
            }
        ),
        encoding="utf-8",
    )
    final_path.write_text(
        json.dumps(
            {
                "schema_name": "FinalPaperSectionsDocument",
                "paper": {"title": "None"},
                "sections": [],
            }
        ),
        encoding="utf-8",
    )

    stats = MODULE.backfill_docling_titles(
        docling_dir=tmp_path / "03_docling_heuristics",
        metadata_titles={"10.1000/demo": "Example Paper"},
        relations_map={"10.1000/demo": {"attachment_path_raw": "storage:Author - 2024 - Example Paper.pdf"}},
        dry_run=False,
    )

    filtered_payload = json.loads(filtered_path.read_text(encoding="utf-8"))
    final_payload = json.loads(final_path.read_text(encoding="utf-8"))

    assert filtered_payload["paper_title"] == "Example Paper"
    assert final_payload["paper"]["title"] == "Example Paper"
    assert stats["filtered_updated"] == 1
    assert stats["final_updated"] == 1
    assert stats["resolved_from_relations"] == 1


def test_build_stats_rows_and_write_csv(tmp_path: Path, monkeypatch) -> None:
    filtered_path = tmp_path / "doi-10.1000-demo.filtered.json"
    final_path = tmp_path / "doi-10.1000-demo.final.json"
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    claims_path = claims_dir / "doi-10.1000-demo.claims.json"

    filtered_path.write_text(
        json.dumps(
            {
                "paper_title": "Example Paper",
                "sections": [
                    {"title": "Methods", "text": "Body", "subsections": []},
                    {"title": "Results", "text": "Body", "subsections": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    final_path.write_text(
        json.dumps(
            {
                "paper": {"title": "Example Paper"},
                "sections": [{"title": "Results", "text": "Body", "subsections": []}],
            }
        ),
        encoding="utf-8",
    )
    claims_path.write_text(json.dumps([{"claim_text": "a"}, {"claim_text": "b"}]), encoding="utf-8")

    monkeypatch.setattr(
        MODULE,
        "load_registry",
        lambda: {
            "10.1000/demo": {
                "base_name": "doi-10.1000-demo",
                "document_id": "DOC123",
                "paths": {
                    "filtered_json": str(filtered_path),
                    "final_json": str(final_path),
                    "claims": str(claims_path),
                    "docling_json": str(tmp_path / "doi-10.1000-demo.json"),
                },
                "stage_status": {
                    "metadata": True,
                    "pdf": True,
                    "heuristics": True,
                    "claims": True,
                    "completed": True,
                },
            }
        },
    )

    rows = MODULE.build_stats_rows(
        relations_map={
            "10.1000/demo": {
                "attachment_path_raw": "storage:Author - 2024 - Example Paper.pdf",
                "resolved_pdf_path": "storage/ABC/Author - 2024 - Example Paper.pdf",
            }
        },
        metadata_titles={"10.1000/demo": "Example Paper"},
        claims_dir=claims_dir,
    )

    assert len(rows) == 1
    assert rows[0]["paper_title"] == "Example Paper"
    assert rows[0]["claims_count"] == 2
    assert rows[0]["filtered_total_sections"] == 2
    assert rows[0]["final_total_sections"] == 1

    output_csv = tmp_path / "pipeline_stats.csv"
    MODULE.write_stats_csv(rows, output_csv)

    with output_csv.open(encoding="utf-8", newline="") as handle:
        exported = list(csv.DictReader(handle))

    assert len(exported) == 1
    assert exported[0]["doi"] == "10.1000/demo"
    assert exported[0]["paper_title"] == "Example Paper"
