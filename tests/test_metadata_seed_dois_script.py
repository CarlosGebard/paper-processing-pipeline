from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "generate_metadata_seed_dois.py"
SPEC = importlib.util.spec_from_file_location("generate_metadata_seed_dois", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_load_keyword_dictionary_ignores_comments_and_normalizes(tmp_path: Path) -> None:
    terms_file = tmp_path / "terms.txt"
    terms_file.write_text("# comment\nDiet\nmacronutrients\n\nDiet\n", encoding="utf-8")

    keywords = MODULE.load_keyword_dictionary(terms_file)

    assert keywords == ["diet", "macronutrients"]


def test_find_matching_keywords_supports_prefix_and_phrase_matching() -> None:
    matched = MODULE.find_matching_keywords(
        "Dietary protein intake and fatty acid balance in adults",
        ["diet", "protein", "fatty acid", "micronutrient"],
    )

    assert matched == ["diet", "protein", "fatty acid"]


def test_collect_candidate_rows_filters_by_keywords_explored_and_citations(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "keep-1.metadata.json").write_text(
        json.dumps(
            {
                "doi": "10.1000/keep-1",
                "title": "Dietary protein patterns in adults",
                "abstract": "Protein intake was measured after diet changes.",
                "citationCount": 500,
            }
        ),
        encoding="utf-8",
    )
    (metadata_dir / "drop-low-citations.metadata.json").write_text(
        json.dumps(
            {
                "doi": "10.1000/drop-low",
                "title": "Diet quality overview",
                "abstract": "Diet discussed broadly.",
                "citationCount": 20,
            }
        ),
        encoding="utf-8",
    )
    (metadata_dir / "drop-explored.metadata.json").write_text(
        json.dumps(
            {
                "doi": "10.1000/drop-explored",
                "title": "Macronutrient balance study",
                "abstract": "Macronutrients and meal timing.",
                "citationCount": 900,
            }
        ),
        encoding="utf-8",
    )
    (metadata_dir / "drop-no-match.metadata.json").write_text(
        json.dumps(
            {
                "doi": "10.1000/drop-nomatch",
                "title": "Astrophysics observations",
                "abstract": "No nutrition content here.",
                "citationCount": 800,
            }
        ),
        encoding="utf-8",
    )

    rows = MODULE.collect_candidate_rows(
        metadata_dir,
        explored_dois={"10.1000/drop-explored"},
        keywords=["diet", "protein", "macronutrient"],
        min_citations=100,
    )

    assert rows == [
        {
            "doi": "10.1000/keep-1",
            "title": "Dietary protein patterns in adults",
            "citation_count": 500,
            "matched_keywords": ["diet", "protein"],
        }
    ]


def test_write_doi_output_writes_one_doi_per_line_with_limit(tmp_path: Path) -> None:
    output_path = tmp_path / "generated_seed_dois.txt"
    rows = [
        {"doi": "10.1000/a", "title": "A", "citation_count": 300, "matched_keywords": ["diet"]},
        {"doi": "10.1000/b", "title": "B", "citation_count": 200, "matched_keywords": ["protein"]},
    ]

    written = MODULE.write_doi_output(rows, output_path, limit=1)

    assert written == 1
    assert output_path.read_text(encoding="utf-8") == "10.1000/a\n"
