from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.docling_heuristics_pipeline.filtered_document import build_filtered_document
from src.docling_heuristics_pipeline.final_document import build_final_document
from src.docling_heuristics_pipeline.converter import (
    convert_pdf_for_pipeline,
    export_conversion_outputs,
)
from src.docling_heuristics_pipeline.logical_document import build_logical_document


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
        assert input_pdf.name == "doi-10.1000-demo.pdf"
        assert output_root_dir == tmp_path / "docling_heuristics"
        assert metadata_dir == tmp_path / "metadata"
        assert dotenv_path == tmp_path / ".env"
        return {
            "output_dir": str(output_root_dir / "doi-10.1000-demo"),
            "json_path": str(output_root_dir / "doi-10.1000-demo" / "doi-10.1000-demo.json"),
            "filtered_json_path": str(output_root_dir / "doi-10.1000-demo" / "doi-10.1000-demo.filtered.json"),
            "final_json_path": str(output_root_dir / "doi-10.1000-demo" / "doi-10.1000-demo.final.json"),
            "json_clean": {"schema_name": "DoclingDocument"},
            "filtered_json": {"schema_name": "FilteredCleanDoclingDocument"},
            "final_json": {
                "schema_name": "FinalPaperSectionsDocument",
                "paper": {"title": "Example paper"},
                "sections": [{"title": "Methods", "text": "Example body", "subsections": []}],
            },
        }

    monkeypatch.setattr(
        "src.docling_heuristics_pipeline.converter.convert_pdf",
        fake_convert_pdf,
    )

    pdf_path = tmp_path / "doi-10.1000-demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    result = convert_pdf_for_pipeline(
        input_pdf=pdf_path,
        output_root_dir=output_root_dir,
        metadata_dir=metadata_dir,
        dotenv_path=tmp_path / ".env",
        document_id="DOC123",
        doi="10.1000/demo",
        base_name="doi-10.1000-demo",
    )

    assert Path(result["output_dir"]).name == "doi-10.1000-demo"
    assert Path(result["json_path"]).name == "doi-10.1000-demo.json"
    assert Path(result["filtered_json_path"]).name == "doi-10.1000-demo.filtered.json"
    assert Path(result["final_json_path"]).name == "doi-10.1000-demo.final.json"


def test_export_conversion_outputs_moves_intermediate_files_into_pdf_subdir(tmp_path) -> None:
    result = export_conversion_outputs(
        output_root_dir=tmp_path,
        input_pdf=tmp_path / "doi-10.1000-demo.pdf",
        json_clean={"schema_name": "DoclingDocument"},
        filtered_json={"schema_name": "FilteredCleanDoclingDocument"},
        final_json={"schema_name": "FinalPaperSectionsDocument"},
    )

    output_dir = Path(result["output_dir"])
    assert output_dir.name == "doi-10.1000-demo"

    json_path = Path(result["json_path"])
    filtered_path = Path(result["filtered_json_path"])
    final_path = Path(result["final_json_path"])

    assert json_path.exists()
    assert filtered_path.exists()
    assert final_path.exists()
    assert json_path.parent == tmp_path / "doi-10.1000-demo"

    json_payload = json.loads(json_path.read_text(encoding="utf-8"))
    filtered_payload = json.loads(filtered_path.read_text(encoding="utf-8"))
    final_payload = json.loads(final_path.read_text(encoding="utf-8"))

    assert json_payload["schema_name"] == "DoclingDocument"
    assert filtered_payload["schema_name"] == "FilteredCleanDoclingDocument"
    assert final_payload["schema_name"] == "FinalPaperSectionsDocument"


def test_build_logical_document_keeps_table_content_in_section_text() -> None:
    logical = build_logical_document(
        {
            "name": "doi-10.1000-demo.pdf",
            "version": "1.0",
            "texts": [
                {"label": "section_header", "text": "Results", "level": 1},
                {"label": "text", "text": "Lead paragraph before table."},
            ],
            "tables": [
                {
                    "caption": "Primary outcomes",
                    "rows": [
                        [{"text": "Group"}, {"text": "Weight loss"}],
                        [{"text": "Intervention"}, {"text": "5 kg"}],
                    ],
                }
            ],
            "groups": [],
            "pictures": [],
            "key_value_items": [],
            "body": {
                "children": [
                    {"$ref": "#/texts/0"},
                    {"$ref": "#/texts/1"},
                    {"$ref": "#/tables/0"},
                ]
            },
        }
    )

    section_text = logical["sections"][0]["text"]
    assert "Lead paragraph before table." in section_text
    assert "Table: Primary outcomes" in section_text
    assert "Group | Weight loss" in section_text
    assert "Intervention | 5 kg" in section_text


def test_build_logical_document_renders_docling_table_cells_grid() -> None:
    logical = build_logical_document(
        {
            "name": "doi-10.1000-demo.pdf",
            "version": "1.0",
            "texts": [
                {"label": "section_header", "text": "Results", "level": 1},
                {"label": "text", "text": "Lead paragraph before table."},
                {"label": "text", "text": "Table 1. Baseline characteristics."},
                {"label": "text", "text": "* Values are mean ± SD."},
            ],
            "tables": [
                {
                    "label": "table",
                    "captions": [{"$ref": "#/texts/2"}],
                    "footnotes": [{"$ref": "#/texts/3"}],
                    "data": {
                        "table_cells": [
                            {"start_row_offset_idx": 0, "end_row_offset_idx": 1, "start_col_offset_idx": 0, "end_col_offset_idx": 1, "text": "Group"},
                            {"start_row_offset_idx": 0, "end_row_offset_idx": 1, "start_col_offset_idx": 1, "end_col_offset_idx": 2, "text": "Weight loss"},
                            {"start_row_offset_idx": 1, "end_row_offset_idx": 2, "start_col_offset_idx": 0, "end_col_offset_idx": 1, "text": "Intervention"},
                            {"start_row_offset_idx": 1, "end_row_offset_idx": 2, "start_col_offset_idx": 1, "end_col_offset_idx": 2, "text": "5 kg"},
                        ]
                    },
                }
            ],
            "groups": [],
            "pictures": [],
            "key_value_items": [],
            "body": {
                "children": [
                    {"$ref": "#/texts/0"},
                    {"$ref": "#/texts/1"},
                    {"$ref": "#/tables/0"},
                ]
            },
        }
    )

    section_text = logical["sections"][0]["text"]
    assert "Table: Table 1. Baseline characteristics." in section_text
    assert "Group | Weight loss" in section_text
    assert "Intervention | 5 kg" in section_text
    assert "* Values are mean ± SD." in section_text


def test_build_final_document_includes_citation_count_from_metadata(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    source_name = "doi-10.1000-demo"
    (metadata_dir / f"{source_name}.metadata.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "paperId": "DOC123",
                    "title": "Example paper",
                    "year": 2024,
                    "doi": "10.1000/demo",
                    "citationCount": 420,
                    "authors": ["Ada Lovelace"],
                }
            }
        ),
        encoding="utf-8",
    )

    result = build_final_document(
        {
            "source": {"name": source_name},
            "paper_title": "Fallback title",
            "sections": [{"title": "Methods", "text": "Body", "subsections": []}],
        },
        metadata_dir=metadata_dir,
    )

    assert result["paper"]["citation_count"] == 420


def test_build_final_document_requires_metadata_title(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    with pytest.raises(ValueError, match="No canonical metadata found"):
        build_final_document(
            {
                "source": {"name": "doi-10.1000-demo"},
                "paper_title": "Legacy title",
                "sections": [{"title": "Methods", "text": "Body content with enough words to survive pruning safely.", "subsections": []}],
            },
            metadata_dir=metadata_dir,
        )


def test_build_filtered_document_requires_metadata_title(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    with pytest.raises(ValueError, match="No canonical metadata found"):
        build_filtered_document(
            {
                "source": {"name": "doi-10.1000-demo"},
                "sections": [{"title": "Methods", "level": 1, "text": "This section has enough words to remain after filtered pruning safely.", "subsections": []}],
            },
            metadata_dir=metadata_dir,
        )


def test_build_final_document_prunes_empty_and_short_leaf_sections(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    source_name = "doi-10.1000-demo"
    (metadata_dir / f"{source_name}.metadata.json").write_text(
        json.dumps({"metadata": {"title": "Example paper"}}),
        encoding="utf-8",
    )

    result = build_final_document(
        {
            "source": {"name": source_name},
            "paper_title": "Fallback title",
            "sections": [
                {"title": "Methods", "text": "This section has enough words to remain in the final output safely.", "subsections": []},
                {"title": "Empty", "text": "   ", "subsections": []},
                {"title": "Short", "text": "too short to keep here", "subsections": []},
            ],
        },
        metadata_dir=metadata_dir,
    )

    assert [section["title"] for section in result["sections"]] == ["Methods"]


def test_build_final_document_keeps_short_parent_when_subsections_have_content(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    source_name = "doi-10.1000-demo"
    (metadata_dir / f"{source_name}.metadata.json").write_text(
        json.dumps({"metadata": {"title": "Example paper"}}),
        encoding="utf-8",
    )

    result = build_final_document(
        {
            "source": {"name": source_name},
            "paper_title": "Fallback title",
            "sections": [
                {
                    "title": "Results",
                    "text": "brief intro",
                    "subsections": [
                        {
                            "title": "Outcome A",
                            "text": "This subsection contains enough detail and words to remain available downstream.",
                            "subsections": [],
                        },
                        {"title": "Outcome B", "text": "short text", "subsections": []},
                    ],
                }
            ],
        },
        metadata_dir=metadata_dir,
    )

    assert len(result["sections"]) == 1
    assert result["sections"][0]["title"] == "Results"
    assert [section["title"] for section in result["sections"][0]["subsections"]] == ["Outcome A"]


def test_build_filtered_document_prunes_empty_and_short_leaf_sections(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    source_name = "doi-10.1000-demo"
    (metadata_dir / f"{source_name}.metadata.json").write_text(
        json.dumps({"metadata": {"title": "Example paper"}}),
        encoding="utf-8",
    )

    result = build_filtered_document(
        {
            "source": {"name": source_name},
            "sections": [
                {"title": "Methods", "level": 1, "text": "This section has enough words to remain after filtered pruning safely.", "subsections": []},
                {"title": "Results", "level": 1, "text": "short text", "subsections": []},
                {"title": "Design", "level": 2, "text": "   ", "subsections": []},
            ],
        },
        metadata_dir=metadata_dir,
    )

    assert [section["title"] for section in result["sections"]] == ["Methods"]


def test_build_filtered_document_keeps_short_parent_when_subsections_have_content(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    source_name = "doi-10.1000-demo"
    (metadata_dir / f"{source_name}.metadata.json").write_text(
        json.dumps({"metadata": {"title": "Example paper"}}),
        encoding="utf-8",
    )

    result = build_filtered_document(
        {
            "source": {"name": source_name},
            "sections": [
                {
                    "title": "Methods",
                    "level": 1,
                    "text": "brief intro",
                    "subsections": [
                        {
                            "title": "Protocol",
                            "level": 2,
                            "text": "This subsection contains enough detailed content to remain after filtering safely.",
                            "subsections": [],
                        },
                        {"title": "Notes", "level": 2, "text": "tiny text", "subsections": []},
                    ],
                }
            ],
        },
        metadata_dir=metadata_dir,
    )

    assert len(result["sections"]) == 1
    assert result["sections"][0]["title"] == "Methods"
    assert [section["title"] for section in result["sections"][0]["subsections"]] == ["Protocol"]


def test_build_filtered_document_keeps_short_leaf_section_with_table_content(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    source_name = "doi-10.1000-demo"
    (metadata_dir / f"{source_name}.metadata.json").write_text(
        json.dumps({"metadata": {"title": "Example paper"}}),
        encoding="utf-8",
    )

    result = build_filtered_document(
        {
            "source": {"name": source_name},
            "sections": [
                {"title": "Results", "level": 1, "text": "Table: Table 1.\nA | B", "subsections": []},
            ],
        },
        metadata_dir=metadata_dir,
    )

    assert [section["title"] for section in result["sections"]] == ["Results"]


def test_build_final_document_keeps_short_leaf_section_with_table_content(tmp_path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    source_name = "doi-10.1000-demo"
    (metadata_dir / f"{source_name}.metadata.json").write_text(
        json.dumps({"metadata": {"title": "Example paper"}}),
        encoding="utf-8",
    )

    result = build_final_document(
        {
            "source": {"name": source_name},
            "paper_title": "Fallback title",
            "sections": [
                {"title": "Results", "text": "Table: Table 1.\nA | B", "subsections": []},
            ],
        },
        metadata_dir=metadata_dir,
    )

    assert [section["title"] for section in result["sections"]] == ["Results"]
