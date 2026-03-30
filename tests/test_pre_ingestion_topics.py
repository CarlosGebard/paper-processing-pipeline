from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

from src.tools.pre_ingestion_topics import (
    bootstrap_candidate_terms_from_citations,
    build_draft_topics_yaml_payload,
    audit_topics,
    candidate_term_rows_to_csv,
    build_topic_cooccurrence_rows,
    build_unmapped_term_rows,
    filter_papers_by_year,
    load_topics_dictionary,
    normalize_keyword,
    normalize_text,
    tokenize_title,
    PaperRecord,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    script_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOPIC_AUDIT_SCRIPT = _load_script_module(
    "pre_ingestion_topic_audit",
    "ops/scripts/pre_ingestion_topic_audit.py",
)
TOPIC_BOOTSTRAP_SCRIPT = _load_script_module(
    "draft_topics_from_metadata_citations",
    "ops/scripts/draft_topics_from_metadata_citations.py",
)
PRE_INGESTION_PAPERS_CSV_SCRIPT = _load_script_module(
    "export_pre_ingestion_papers_csv",
    "ops/scripts/reporting/export_pre_ingestion_papers_csv.py",
)


def test_normalization_and_tokenization_are_deterministic() -> None:
    assert normalize_text("Vitamin D, Obesity & 25-OHD!") == "vitamin d obesity 25 ohd"
    assert tokenize_title("The Gut Microbiome in Obesity and Type 2 Diabetes") == [
        "gut",
        "microbiome",
        "obesity",
        "type",
        "2",
        "diabetes",
    ]
    assert normalize_keyword("Randomized Controlled Trial") == "randomized controlled trial"


def test_topic_mapping_and_unmapped_terms(tmp_path: Path) -> None:
    topics_path = tmp_path / "topics.yaml"
    topics_path.write_text(
        (
            "topics:\n"
            "  vitamin_d:\n"
            "    keywords:\n"
            "      - vitamin d\n"
            "      - 25-ohd\n"
            "  obesity:\n"
            "    keywords:\n"
            "      - obesity\n"
            "      - overweight\n"
            "  study_design_rct:\n"
            "    keywords:\n"
            "      - randomized controlled trial\n"
        ),
        encoding="utf-8",
    )
    topics = load_topics_dictionary(topics_path)
    papers = [
        PaperRecord(
            paper_id="p1",
            title="Vitamin D supplementation and obesity in adults",
            year=2024,
        ),
        PaperRecord(
            paper_id="p2",
            title="Randomized controlled trial of 25-OHD in overweight adults",
            year=2023,
        ),
        PaperRecord(
            paper_id="p3",
            title="Sleep duration and cardiometabolic outcomes",
            year=2022,
        ),
    ]

    audit = audit_topics(papers, topics)

    assert [match.topic for match in audit.topic_matches["p1"]] == ["vitamin_d", "obesity"]
    assert [match.topic for match in audit.topic_matches["p2"]] == ["vitamin_d", "obesity", "study_design_rct"]
    assert audit.topic_matches["p3"] == ()

    unmapped_rows = build_unmapped_term_rows(audit, min_doc_freq=1)
    unmapped_terms = {row["term"] for row in unmapped_rows}
    assert "sleep" in unmapped_terms
    assert "cardiometabolic" in unmapped_terms
    assert "vitamin d" not in unmapped_terms

    cooccurrence_rows = build_topic_cooccurrence_rows(audit)
    assert {"topic_a": "obesity", "topic_b": "vitamin_d", "count": 2} in cooccurrence_rows


def test_filter_papers_by_year_excludes_missing_year_when_filtering() -> None:
    papers = [
        PaperRecord(paper_id="p1", title="A", year=2024),
        PaperRecord(paper_id="p2", title="B", year=2020),
        PaperRecord(paper_id="p3", title="C", year=None),
    ]

    filtered = filter_papers_by_year(papers, min_year=2021)

    assert [paper.paper_id for paper in filtered] == ["p1"]


def test_script_exports_required_artifacts(tmp_path: Path) -> None:
    input_csv = tmp_path / "papers.csv"
    topics_yaml = tmp_path / "topics.yaml"
    output_dir = tmp_path / "artifacts"

    input_csv.write_text(
        (
            "paper_id,title,year,doi,journal\n"
            "p1,Vitamin D supplementation in adults with obesity,2024,10.1000/demo-1,Journal A\n"
            "p2,Gut microbiome dysbiosis in obesity,2023,10.1000/demo-2,Journal B\n"
            "p3,Sleep duration and cardiometabolic health,2021,10.1000/demo-3,Journal C\n"
        ),
        encoding="utf-8",
    )
    topics_yaml.write_text(
        (
            "topics:\n"
            "  vitamin_d:\n"
            "    keywords:\n"
            "      - vitamin d\n"
            "  obesity:\n"
            "    keywords:\n"
            "      - obesity\n"
            "  gut_microbiome:\n"
            "    keywords:\n"
            "      - gut microbiome\n"
            "      - dysbiosis\n"
        ),
        encoding="utf-8",
    )

    papers = TOPIC_AUDIT_SCRIPT.load_papers(input_csv)
    topics = TOPIC_AUDIT_SCRIPT.load_topics_dictionary(topics_yaml)
    audit = TOPIC_AUDIT_SCRIPT.audit_topics(papers, topics)
    outputs = TOPIC_AUDIT_SCRIPT.export_audit_artifacts(audit, output_dir, unmapped_min_doc_freq=1)

    for output_path in outputs.values():
        assert output_path.exists()

    with (output_dir / "paper_topics.csv").open(encoding="utf-8", newline="") as handle:
        paper_rows = list(csv.DictReader(handle))

    assert len(paper_rows) == 3
    assert paper_rows[0]["paper_id"] == "p1"
    assert "vitamin_d" in paper_rows[0]["matched_topics"]

    with (output_dir / "unclassified_papers.csv").open(encoding="utf-8", newline="") as handle:
        unclassified_rows = list(csv.DictReader(handle))

    assert len(unclassified_rows) == 1
    assert unclassified_rows[0]["paper_id"] == "p3"

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["paper_count"] == 3
    assert summary["unclassified_paper_count"] == 1


def test_pre_ingestion_topic_audit_defaults_to_csv_workspace(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["pre_ingestion_topic_audit.py", "--input", "papers.csv", "--topics", "topics.yaml"],
    )

    args = TOPIC_AUDIT_SCRIPT.parse_args()

    assert args.output_dir == TOPIC_AUDIT_SCRIPT.ctx.PRE_INGESTION_AUDIT_DIR


def test_bootstrap_candidate_terms_prioritizes_specific_repeated_terms() -> None:
    papers = [
        PaperRecord(
            paper_id="p1",
            title="Gut microbiota metabolism of L-carnitine promotes atherosclerosis",
            citation_count=3957,
        ),
        PaperRecord(
            paper_id="p2",
            title="Impact of diet in shaping gut microbiota in children",
            citation_count=5182,
        ),
        PaperRecord(
            paper_id="p3",
            title="Gut microbiota from twins discordant for obesity modulate metabolism",
            citation_count=3424,
        ),
    ]

    rows = bootstrap_candidate_terms_from_citations(
        papers,
        min_doc_freq=2,
        top_n=10,
    )

    terms = [row.term for row in rows]
    assert "gut microbiota" in terms
    assert "clinical practice guidelines" not in terms


def test_draft_topics_script_writes_ranked_candidate_csv(tmp_path: Path) -> None:
    input_csv = tmp_path / "metadata_citations.csv"
    output_csv = tmp_path / "candidate_terms.csv"
    input_csv.write_text(
        (
            "title,citation_count\n"
            "\"Gut microbiota in obesity\",500\n"
            "\"Gut microbiota and type 2 diabetes\",700\n"
            "\"Mediterranean diet and cardiovascular disease\",900\n"
        ),
        encoding="utf-8",
    )

    papers = TOPIC_BOOTSTRAP_SCRIPT.load_metadata_citations_as_papers(input_csv)
    candidates = TOPIC_BOOTSTRAP_SCRIPT.bootstrap_candidate_terms_from_citations(
        papers,
        min_doc_freq=2,
        top_n=20,
    )
    rows = TOPIC_BOOTSTRAP_SCRIPT.candidate_term_rows_to_csv(candidates)
    TOPIC_BOOTSTRAP_SCRIPT.write_csv_rows(
        rows,
        output_csv,
        ["term", "n_tokens", "doc_freq", "total_freq", "citation_weight", "combined_score", "example_titles"],
    )

    with output_csv.open(encoding="utf-8", newline="") as handle:
        exported = list(csv.DictReader(handle))

    assert exported
    assert exported[0]["term"] == "gut microbiota"
    assert float(exported[0]["combined_score"]) > 0.0


def test_draft_topics_script_defaults_to_csv_workspace(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["draft_topics_from_metadata_citations.py"])

    args = TOPIC_BOOTSTRAP_SCRIPT.parse_args()

    assert args.output_csv == TOPIC_BOOTSTRAP_SCRIPT.ctx.PRE_INGESTION_CANDIDATE_TERMS_CSV
    assert args.output_yaml == TOPIC_BOOTSTRAP_SCRIPT.ctx.PRE_INGESTION_DRAFT_TOPICS_YAML


def test_candidate_term_rows_to_csv_serializes_examples() -> None:
    rows = bootstrap_candidate_terms_from_citations(
        [
            PaperRecord(
                paper_id="p1",
                title="Mediterranean diet and cardiovascular disease",
                citation_count=3506,
            ),
            PaperRecord(
                paper_id="p2",
                title="Adherence to a Mediterranean diet and survival",
                citation_count=4179,
            ),
        ],
        min_doc_freq=2,
        top_n=10,
    )

    csv_rows = candidate_term_rows_to_csv(rows)

    assert csv_rows
    assert " | " in csv_rows[0]["example_titles"]


def test_build_draft_topics_yaml_payload_groups_terms_into_topics() -> None:
    rows = bootstrap_candidate_terms_from_citations(
        [
            PaperRecord(paper_id="p1", title="Gut microbiota in obesity", citation_count=500),
            PaperRecord(paper_id="p2", title="Gut microbiome and dysbiosis in obesity", citation_count=400),
            PaperRecord(paper_id="p3", title="Vitamin D and type 2 diabetes", citation_count=700),
            PaperRecord(paper_id="p4", title="Heart disease and cardiovascular disease prevention", citation_count=900),
        ],
        min_doc_freq=1,
        top_n=50,
    )

    payload = build_draft_topics_yaml_payload(rows)

    assert "topics" in payload
    assert "gut_microbiome" in payload["topics"]
    assert "vitamin_d" in payload["topics"]
    assert "cardiovascular_disease" in payload["topics"]
    assert "review_candidates" in payload


def test_read_metadata_rows_exports_canonical_pre_ingestion_fields(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    (metadata_dir / "paper-1.metadata.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "document_id": "DOC001",
                    "title": "Vitamin D and obesity",
                    "year": 2024,
                    "doi": "10.1000/demo-1",
                    "journal": "Journal A",
                }
            }
        ),
        encoding="utf-8",
    )
    (metadata_dir / "paper-2.metadata.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "paperId": "S2-123",
                    "title": "Gut microbiome in diabetes",
                    "venue": "Journal B",
                }
            }
        ),
        encoding="utf-8",
    )

    rows = PRE_INGESTION_PAPERS_CSV_SCRIPT.read_metadata_rows(metadata_dir)
    output_csv = tmp_path / "papers.csv"
    PRE_INGESTION_PAPERS_CSV_SCRIPT.write_csv(rows, output_csv)

    with output_csv.open(encoding="utf-8", newline="") as handle:
        exported = list(csv.DictReader(handle))

    assert exported == [
        {
            "paper_id": "S2-123",
            "title": "Gut microbiome in diabetes",
            "year": "",
            "doi": "",
            "journal": "Journal B",
        },
        {
            "paper_id": "DOC001",
            "title": "Vitamin D and obesity",
            "year": "2024",
            "doi": "10.1000/demo-1",
            "journal": "Journal A",
        },
    ]
