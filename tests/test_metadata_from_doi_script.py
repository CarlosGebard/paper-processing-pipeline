from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "create_metadata_from_doi.py"
SPEC = importlib.util.spec_from_file_location("create_metadata_from_doi", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_build_metadata_payload_matches_canonical_shape() -> None:
    payload = MODULE.build_metadata_payload(
        {
            "paperId": "paper-1",
            "title": "Example Paper",
            "year": 2024,
            "citationCount": 321,
            "externalIds": {"DOI": "10.1000/demo", "ArXiv": "2401.12345"},
            "openAccessPdf": {"url": "https://example.test/demo.pdf"},
            "abstract": "Example abstract",
            "authors": [{"name": "Ada Lovelace"}, {"name": "Alan Turing"}],
        }
    )

    assert payload == {
        "paperId": "paper-1",
        "title": "Example Paper",
        "year": 2024,
        "citationCount": 321,
        "doi": "10.1000/demo",
        "arxiv": "2401.12345",
        "pdf_url": "https://example.test/demo.pdf",
        "abstract": "Example abstract",
        "parent_papers": [],
        "authors": ["Ada Lovelace", "Alan Turing"],
    }


def test_write_metadata_for_doi_writes_canonical_file(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "metadata"
    session = object()

    def fake_fetch(_session: object, doi: str) -> dict[str, object]:
        assert _session is session
        assert doi == "10.1000/demo"
        return {
            "paperId": "paper-1",
            "title": "Example Paper",
            "year": 2024,
            "citationCount": 321,
            "externalIds": {"DOI": "10.1000/demo"},
            "openAccessPdf": {"url": "https://example.test/demo.pdf"},
            "abstract": "Example abstract",
            "authors": [{"name": "Ada Lovelace"}],
        }

    monkeypatch.setattr(MODULE, "fetch_paper_by_doi", fake_fetch)

    output_path, status = MODULE.write_metadata_for_doi(
        "10.1000/demo",
        output_dir=output_dir,
        session=session,
        overwrite=False,
    )

    assert status == "written"
    assert output_path == output_dir / "doi-10.1000-demo.metadata.json"
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "paperId": "paper-1",
        "title": "Example Paper",
        "year": 2024,
        "citationCount": 321,
        "doi": "10.1000/demo",
        "arxiv": None,
        "pdf_url": "https://example.test/demo.pdf",
        "abstract": "Example abstract",
        "parent_papers": [],
        "authors": ["Ada Lovelace"],
    }


def test_write_metadata_for_doi_skips_existing_by_default(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "metadata"
    output_dir.mkdir()
    existing_path = output_dir / "doi-10.1000-demo.metadata.json"
    existing_path.write_text('{"existing": true}\n', encoding="utf-8")
    session = object()

    def fake_fetch(_session: object, doi: str) -> dict[str, object]:
        return {
            "paperId": "paper-1",
            "title": "Example Paper",
            "year": 2024,
            "citationCount": 321,
            "externalIds": {"DOI": doi},
            "openAccessPdf": {},
            "abstract": None,
            "authors": [],
        }

    monkeypatch.setattr(MODULE, "fetch_paper_by_doi", fake_fetch)

    output_path, status = MODULE.write_metadata_for_doi(
        "10.1000/demo",
        output_dir=output_dir,
        session=session,
        overwrite=False,
    )

    assert status == "skipped_existing"
    assert output_path == existing_path
    assert existing_path.read_text(encoding="utf-8") == '{"existing": true}\n'


def test_write_metadata_for_doi_overwrites_when_requested(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "metadata"
    output_dir.mkdir()
    existing_path = output_dir / "doi-10.1000-demo.metadata.json"
    existing_path.write_text('{"existing": true}\n', encoding="utf-8")
    session = object()

    def fake_fetch(_session: object, doi: str) -> dict[str, object]:
        return {
            "paperId": "paper-1",
            "title": "Updated Paper",
            "year": 2025,
            "citationCount": 500,
            "externalIds": {"DOI": doi},
            "openAccessPdf": {},
            "abstract": "Updated abstract",
            "authors": [{"name": "Author One"}],
        }

    monkeypatch.setattr(MODULE, "fetch_paper_by_doi", fake_fetch)

    output_path, status = MODULE.write_metadata_for_doi(
        "10.1000/demo",
        output_dir=output_dir,
        session=session,
        overwrite=True,
    )

    assert status == "written"
    assert output_path == existing_path
    assert json.loads(existing_path.read_text(encoding="utf-8"))["title"] == "Updated Paper"
