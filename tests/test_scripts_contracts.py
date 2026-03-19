from __future__ import annotations

import json
from pathlib import Path

from json_to_bib import generate_bib
from normalize_raw_pdfs import _guess_base_name_from_stem, sync_raw_pdfs_into_input


def test_generate_bib_creates_entry_from_metadata_wrapper(tmp_path: Path) -> None:
    input_dir = tmp_path / "metadata"
    input_dir.mkdir()
    output_bib = tmp_path / "papers.bib"

    record = {
        "metadata": {
            "document_id": "DOC123",
            "doi": "10.1000/demo",
            "title": "Example Paper",
            "year": 2024,
            "authors": ["Ada Lovelace", "Alan Turing"],
        }
    }
    (input_dir / "record.json").write_text(json.dumps(record), encoding="utf-8")

    entries, skipped = generate_bib(input_dir, output_bib)

    assert entries == 1
    assert skipped == 0
    content = output_bib.read_text(encoding="utf-8")
    assert "@article{Lovelace2024" in content
    assert "doi = {10.1000/demo}" in content


def test_sync_raw_pdfs_renames_pdf_from_metadata_match(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    input_dir = tmp_path / "input"
    metadata_dir = tmp_path / "metadata"

    raw_dir.mkdir()
    metadata_dir.mkdir()

    source_pdf = raw_dir / "Example Paper.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n")

    metadata = {
        "metadata": {
            "document_id": "DOC123",
            "doi": "10.1000/demo",
            "title": "Example Paper",
        }
    }
    (metadata_dir / "record.json").write_text(json.dumps(metadata), encoding="utf-8")

    copied, skipped = sync_raw_pdfs_into_input(raw_dir, input_dir, metadata_dir)

    assert copied == 1
    assert skipped == 0
    assert (input_dir / "DOC123__doi-10.1000-demo.pdf").exists()


def test_guess_base_name_handles_truncated_author_year_filename() -> None:
    metadata_records = [
        {
            "document_id": "DOC999",
            "doi": "10.1000/demo",
            "title_key": "effectofsleepextensiononobjectivelyassessedenergyintakeamongadultswithoverweightinreallifesettings",
            "base_name": "DOC999__doi-10.1000-demo",
        }
    ]

    guessed = _guess_base_name_from_stem(
        "Tasali et al. - 2022 - Effect of sleep extension on objectively assessed energy intake among adults with overweight in real",
        metadata_records,
        [],
    )

    assert guessed == "DOC999__doi-10.1000-demo"
