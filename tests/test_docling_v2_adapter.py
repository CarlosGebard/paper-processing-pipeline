from __future__ import annotations

import json
from pathlib import Path

import config_loader as ctx
from paper_pipeline.docling_pipeline.converter import (
    convert_pdf_for_pipeline,
    export_conversion_outputs,
)


def test_convert_pdf_for_pipeline_writes_canonical_outputs(tmp_path, monkeypatch) -> None:
    output_root_dir = tmp_path / "docling_heuristics"
    metadata_dir = tmp_path / "metadata"

    for directory in (
        output_root_dir,
        metadata_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    def fake_convert_pdf(
        input_pdf: Path,
        output_root_dir: Path,
        metadata_dir: Path | None = None,
        dotenv_path: Path | None = None,
    ) -> dict[str, object]:
        assert input_pdf.name == "DOC123__doi-10.1000-demo.pdf"
        assert output_root_dir == tmp_path / "docling_heuristics"
        assert metadata_dir == tmp_path / "metadata"
        assert dotenv_path == tmp_path / ".env"
        return {
            "output_dir": str(output_root_dir / "DOC123__doi-10.1000-demo"),
            "json_path": str(output_root_dir / "DOC123__doi-10.1000-demo" / "DOC123__doi-10.1000-demo.json"),
            "filtered_json_path": str(output_root_dir / "DOC123__doi-10.1000-demo" / "DOC123__doi-10.1000-demo.filtered.json"),
            "final_json_path": str(output_root_dir / "DOC123__doi-10.1000-demo" / "DOC123__doi-10.1000-demo.final.json"),
            "json_clean": {"schema_name": "DoclingDocument"},
            "filtered_json": {"schema_name": "FilteredCleanDoclingDocument"},
            "final_json": {
                "schema_name": "FinalPaperSectionsDocument",
                "paper": {"title": "Example paper"},
                "sections": [{"title": "Methods", "text": "Example body", "subsections": []}],
            },
        }

    monkeypatch.setattr(
        "paper_pipeline.docling_pipeline.converter.convert_pdf",
        fake_convert_pdf,
    )

    pdf_path = tmp_path / "DOC123__doi-10.1000-demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    result = convert_pdf_for_pipeline(
        input_pdf=pdf_path,
        output_root_dir=output_root_dir,
        metadata_dir=metadata_dir,
        dotenv_path=tmp_path / ".env",
        document_id="DOC123",
        doi="10.1000/demo",
        base_name="DOC123__doi-10.1000-demo",
    )

    assert Path(result["output_dir"]).name == "DOC123__doi-10.1000-demo"
    assert Path(result["json_path"]).name == "DOC123__doi-10.1000-demo.json"
    assert Path(result["filtered_json_path"]).name == "DOC123__doi-10.1000-demo.filtered.json"
    assert Path(result["final_json_path"]).name == "DOC123__doi-10.1000-demo.final.json"


def test_export_conversion_outputs_moves_intermediate_files_into_pdf_subdir(tmp_path) -> None:
    result = export_conversion_outputs(
        output_root_dir=tmp_path,
        input_pdf=tmp_path / "DOC123__doi-10.1000-demo.pdf",
        json_clean={"schema_name": "DoclingDocument"},
        filtered_json={"schema_name": "FilteredCleanDoclingDocument"},
        final_json={"schema_name": "FinalPaperSectionsDocument"},
    )

    output_dir = Path(result["output_dir"])
    assert output_dir.name == "DOC123__doi-10.1000-demo"

    json_path = Path(result["json_path"])
    filtered_path = Path(result["filtered_json_path"])
    final_path = Path(result["final_json_path"])

    assert json_path.exists()
    assert filtered_path.exists()
    assert final_path.exists()
    assert json_path.parent == tmp_path / "DOC123__doi-10.1000-demo"

    json_payload = json.loads(json_path.read_text(encoding="utf-8"))
    filtered_payload = json.loads(filtered_path.read_text(encoding="utf-8"))
    final_payload = json.loads(final_path.read_text(encoding="utf-8"))

    assert json_payload["schema_name"] == "DoclingDocument"
    assert filtered_payload["schema_name"] == "FilteredCleanDoclingDocument"
    assert final_payload["schema_name"] == "FinalPaperSectionsDocument"
