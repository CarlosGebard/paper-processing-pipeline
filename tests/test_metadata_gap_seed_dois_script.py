from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "generate_metadata_gap_seed_dois.py"
SPEC = importlib.util.spec_from_file_location("generate_metadata_gap_seed_dois", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_load_gap_topics_normalizes_terms_and_falls_back_to_name(tmp_path: Path) -> None:
    topics_file = tmp_path / "topics.yaml"
    topics_file.write_text(
        "topics:\n"
        "  - name: protein_intake\n"
        "    search_terms: [\"Protein Intake\", \"dietary protein\"]\n"
        "  - name: leucine\n",
        encoding="utf-8",
    )

    topics = MODULE.load_gap_topics(topics_file)

    assert topics == [
        {"name": "protein_intake", "search_terms": ["protein intake", "dietary protein"]},
        {"name": "leucine", "search_terms": ["leucine"]},
    ]


def test_collect_gap_seed_rows_prioritizes_unclassified_and_filters_explored(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "a.metadata.json").write_text(
        json.dumps(
            {
                "doi": "10.1000/a",
                "title": "Leucine supplementation for sarcopenia",
                "abstract": "Leucine and muscle protein synthesis in older adults.",
                "citationCount": 220,
            }
        ),
        encoding="utf-8",
    )
    (metadata_dir / "b.metadata.json").write_text(
        json.dumps(
            {
                "doi": "10.1000/b",
                "title": "Hydration in dialysis nutrition",
                "abstract": "Fluid balance in hemodialysis patients.",
                "citationCount": 180,
            }
        ),
        encoding="utf-8",
    )

    rows = MODULE.collect_gap_seed_rows(
        papers_rows=[
            {"doi": "10.1000/a", "title": "Leucine supplementation for sarcopenia"},
            {"doi": "10.1000/b", "title": "Hydration in dialysis nutrition"},
        ],
        unclassified_rows=[{"doi": "10.1000/b", "title": "Hydration in dialysis nutrition"}],
        metadata_index=MODULE.load_metadata_index(metadata_dir),
        explored_dois={"10.1000/a"},
        topics=[
            {"name": "leucine", "search_terms": ["leucine"]},
            {"name": "dialysis_nutrition", "search_terms": ["dialysis nutrition", "hemodialysis"]},
            {"name": "fluid_balance", "search_terms": ["fluid balance", "hydration"]},
        ],
        min_citations=100,
    )

    assert rows == [
        {
            "doi": "10.1000/b",
            "title": "Hydration in dialysis nutrition",
            "citation_count": 180,
            "matched_topics": ["dialysis_nutrition", "fluid_balance"],
            "source_bucket": "unclassified",
            "score": 225180,
        }
    ]


def test_write_doi_output_writes_ranked_gap_seed_file(tmp_path: Path) -> None:
    output_path = tmp_path / "seed_dois.txt"
    written = MODULE.write_doi_output(
        [
            {"doi": "10.1000/b"},
            {"doi": "10.1000/c"},
        ],
        output_path,
        limit=1,
    )

    assert written == 1
    assert output_path.read_text(encoding="utf-8") == "10.1000/b\n"
