from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "enrich_dirty_metadata_from_titles.py"
SPEC = importlib.util.spec_from_file_location("enrich_dirty_metadata_from_titles", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_choose_best_title_match_prefers_exact_title_and_close_year() -> None:
    candidates = [
        {
            "paperId": "paper-a",
            "title": "Completely Different Paper",
            "year": 2021,
            "externalIds": {},
        },
        {
            "paperId": "paper-b",
            "title": "Omega-3 fatty acids for the primary and secondary prevention of cardiovascular disease.",
            "year": 2018,
            "externalIds": {"DOI": "10.1002/14651858.CD003177.pub4"},
        },
    ]

    decision = MODULE.choose_best_title_match(
        "Omega-3 fatty acids for the primary and secondary prevention of cardiovascular disease.",
        2018,
        candidates,
    )

    assert decision.matched is True
    assert decision.candidate["paperId"] == "paper-b"
    assert decision.ratio == 1.0


def test_build_metadata_payload_matches_canonical_shape() -> None:
    payload = MODULE.build_metadata_payload(
        {
            "paperId": "paper-b",
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
        "paperId": "paper-b",
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


def test_normalize_source_directory_promotes_only_unique_records(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "dirty"
    canonical_dir = tmp_path / "metadata"
    source_dir.mkdir()
    canonical_dir.mkdir()

    existing_payload = {
        "paperId": "paper-existing",
        "title": "Existing Paper",
        "year": 2020,
        "citationCount": 10,
        "doi": "10.1000/existing",
        "arxiv": None,
        "pdf_url": None,
        "abstract": None,
        "parent_papers": [],
        "authors": ["Author One"],
    }
    (canonical_dir / "doi-10.1000-existing.metadata.json").write_text(
        json.dumps(existing_payload),
        encoding="utf-8",
    )

    dirty_existing = {
        "paperId": "dirty-1",
        "title": "Existing Paper",
        "year": 2020,
        "citationCount": 5,
    }
    dirty_new = {
        "paperId": "dirty-2",
        "title": "Novel Paper",
        "year": 2021,
        "citationCount": 8,
    }
    (source_dir / "dirty-existing.json").write_text(json.dumps(dirty_existing), encoding="utf-8")
    (source_dir / "dirty-new.json").write_text(json.dumps(dirty_new), encoding="utf-8")

    def fake_search(_session, *, title: str, limit: int):
        assert limit == 10
        if title == "Existing Paper":
            return [
                {
                    "paperId": "paper-existing",
                    "title": "Existing Paper",
                    "year": 2020,
                    "citationCount": 100,
                    "externalIds": {"DOI": "10.1000/existing"},
                    "openAccessPdf": {"url": "https://example.test/existing.pdf"},
                    "abstract": "Existing abstract",
                    "authors": [{"name": "Author One"}],
                }
            ]
        return [
            {
                "paperId": "paper-new",
                "title": "Novel Paper",
                "year": 2021,
                "citationCount": 200,
                "externalIds": {"DOI": "10.1000/new"},
                "openAccessPdf": {"url": "https://example.test/new.pdf"},
                "abstract": "Novel abstract",
                "authors": [{"name": "Author Two"}],
            }
        ]

    monkeypatch.setattr(MODULE, "search_semantic_scholar_by_title", fake_search)

    stats = MODULE.normalize_source_directory(
        source_dir,
        canonical_metadata_dir=canonical_dir,
        session=object(),
        search_limit=10,
        min_similarity=0.93,
        dry_run=False,
    )

    assert stats["processed"] == 2
    assert stats["matched"] == 2
    assert stats["rewritten"] == 2
    assert stats["promoted"] == 1
    assert stats["duplicates"] == 1

    assert (source_dir / "doi-10.1000-existing.metadata.json").exists()
    assert (source_dir / "doi-10.1000-new.metadata.json").exists()
    assert (canonical_dir / "doi-10.1000-existing.metadata.json").exists()
    assert (canonical_dir / "doi-10.1000-new.metadata.json").exists()
