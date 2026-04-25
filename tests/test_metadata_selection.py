from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import src.stages.metadata as metadata_stage
import src.tools.citation_exploration as citation_exploration
from requests import HTTPError
from src.tools.paper_selector import (
    PaperCandidate,
    build_responses_payload,
    build_user_prompt,
    normalize_decisions,
)


def test_build_selection_preview_limits_to_twenty_words() -> None:
    text = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twentyone twentytwo"

    preview = citation_exploration.build_selection_preview(text, max_words=20)

    assert preview == "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty..."


def test_citation_exploration_import_does_not_create_directories(monkeypatch, tmp_path: Path) -> None:
    module_path = Path(__file__).resolve().parents[1] / "src" / "tools" / "citation_exploration.py"
    spec = importlib.util.spec_from_file_location("citation_exploration_no_mkdir", module_path)
    assert spec and spec.loader
    created: list[Path] = []

    def fake_mkdir(self: Path, parents: bool = False, exist_ok: bool = False) -> None:
        created.append(self)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    assert created == []


def test_paper_to_metadata_record_preserves_canonical_shape() -> None:
    paper = {
        "paperId": "paper-1",
        "title": "Nutrition and metabolism",
        "year": 2024,
        "citationCount": 12,
        "abstract": "A short abstract about diet and metabolism.",
        "externalIds": {"DOI": "10.1000/demo", "ArXiv": "1234.5678"},
        "openAccessPdf": {"url": "https://example.org/paper.pdf"},
        "authors": [{"name": "Ada Lovelace"}, {"name": "Alan Turing"}],
    }

    record = citation_exploration.paper_to_metadata_record(
        paper,
        parent="seed-paper",
        seed_doi="10.1000/seed",
        abstract_word_limit=300,
    )

    assert record == {
        "paperId": "paper-1",
        "title": "Nutrition and metabolism",
        "year": 2024,
        "citationCount": 12,
        "doi": "10.1000/demo",
        "arxiv": "1234.5678",
        "pdf_url": "https://example.org/paper.pdf",
        "abstract": "A short abstract about diet and metabolism.",
        "parent_papers": ["seed-paper"],
        "seed_papers": ["10.1000/seed"],
        "is_seed_paper": False,
        "authors": ["Ada Lovelace", "Alan Turing"],
    }


def test_load_seed_dois_reads_editable_file_and_ignores_comments(tmp_path: Path) -> None:
    doi_file = tmp_path / "seed_dois.txt"
    doi_file.write_text(
        "# comment\n10.1000/Seed-A\n\nhttps://doi.org/10.1000/seed-b\n10.1000/Seed-A\n",
        encoding="utf-8",
    )

    assert citation_exploration.load_seed_dois(doi_file=doi_file, fallback_seed=None) == [
        "10.1000/seed-a",
        "10.1000/seed-b",
    ]


def test_load_seed_dois_returns_empty_when_file_exists_but_queue_is_empty(tmp_path: Path) -> None:
    doi_file = tmp_path / "seed_dois.txt"
    doi_file.write_text("# comment only\n\n", encoding="utf-8")

    assert citation_exploration.load_seed_dois(doi_file=doi_file, fallback_seed="10.1000/fallback") == []


def test_append_completed_seed_doi_persists_unique_normalized_values(tmp_path: Path) -> None:
    doi_file = tmp_path / "completed_seed_dois.txt"
    citation_exploration.append_completed_seed_doi("10.1000/Seed-A", doi_file=doi_file)
    citation_exploration.append_completed_seed_doi("https://doi.org/10.1000/seed-a", doi_file=doi_file)
    citation_exploration.append_completed_seed_doi("10.1000/seed-b", doi_file=doi_file)

    assert doi_file.read_text(encoding="utf-8") == "10.1000/seed-a\n10.1000/seed-b\n"
    assert citation_exploration.load_completed_seed_dois(doi_file=doi_file) == {
        "10.1000/seed-a",
        "10.1000/seed-b",
    }


def test_append_completed_seed_doi_removes_processed_seed_from_queue(tmp_path: Path) -> None:
    source_doi_file = tmp_path / "seed_dois.txt"
    completed_doi_file = tmp_path / "completed_seed_dois.txt"
    source_doi_file.write_text(
        "# keep comment\n10.1000/seed-a\n\nhttps://doi.org/10.1000/seed-b\n10.1000/seed-c\n",
        encoding="utf-8",
    )

    citation_exploration.append_completed_seed_doi(
        "10.1000/Seed-B",
        doi_file=completed_doi_file,
        source_doi_file=source_doi_file,
    )

    assert completed_doi_file.read_text(encoding="utf-8") == "10.1000/seed-b\n"
    assert source_doi_file.read_text(encoding="utf-8") == "# keep comment\n10.1000/seed-a\n\n10.1000/seed-c\n"


def test_sync_seed_doi_queue_removes_all_completed_seeds_from_source_queue(tmp_path: Path) -> None:
    source_doi_file = tmp_path / "seed_dois.txt"
    completed_doi_file = tmp_path / "completed_seed_dois.txt"
    source_doi_file.write_text(
        "# keep comment\n10.1000/seed-a\n10.1000/seed-b\n\n10.1000/seed-c\n",
        encoding="utf-8",
    )
    completed_doi_file.write_text("10.1000/seed-a\n10.1000/seed-c\n", encoding="utf-8")

    citation_exploration.sync_seed_doi_queue(
        source_doi_file=source_doi_file,
        completed_doi_file=completed_doi_file,
    )

    assert source_doi_file.read_text(encoding="utf-8") == "# keep comment\n10.1000/seed-b\n\n"


def test_save_paper_merges_seed_parent_and_seed_marker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(citation_exploration, "papers_dir", tmp_path / "metadata")
    monkeypatch.setattr(citation_exploration, "discarded_dir", tmp_path / "discarded")
    citation_exploration.papers_dir.mkdir(parents=True, exist_ok=True)
    citation_exploration.discarded_dir.mkdir(parents=True, exist_ok=True)

    paper = {
        "paperId": "paper-1",
        "title": "Nutrition and metabolism",
        "year": 2024,
        "citationCount": 12,
        "abstract": "A short abstract about diet and metabolism.",
        "externalIds": {"DOI": "10.1000/demo", "ArXiv": "1234.5678"},
        "openAccessPdf": {"url": "https://example.org/paper.pdf"},
        "authors": [{"name": "Ada Lovelace"}],
    }
    processed: set[str] = set()

    citation_exploration.save_paper(
        paper,
        parent=None,
        seed_doi="10.1000/demo",
        is_seed_paper=True,
        processed_papers=processed,
    )
    citation_exploration.save_paper(
        paper,
        parent="seed-paper-1",
        seed_doi="10.1000/seed-a",
        processed_papers=processed,
    )
    citation_exploration.save_paper(
        paper,
        parent="seed-paper-2",
        seed_doi="10.1000/seed-b",
        processed_papers=processed,
    )

    saved = json.loads((citation_exploration.papers_dir / "doi-10.1000-demo.metadata.json").read_text(encoding="utf-8"))

    assert saved["is_seed_paper"] is True
    assert saved["parent_papers"] == ["seed-paper-1", "seed-paper-2"]
    assert saved["seed_papers"] == ["10.1000/demo", "10.1000/seed-a", "10.1000/seed-b"]
    assert processed == {"paper-1", "doi-10.1000-demo"}


def test_save_paper_persists_parent_metadata_when_parent_payload_is_provided(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(citation_exploration, "papers_dir", tmp_path / "metadata")
    monkeypatch.setattr(citation_exploration, "discarded_dir", tmp_path / "discarded")
    citation_exploration.papers_dir.mkdir(parents=True, exist_ok=True)
    citation_exploration.discarded_dir.mkdir(parents=True, exist_ok=True)

    parent_paper = {
        "paperId": "seed-paper-1",
        "title": "Seed parent",
        "year": 2020,
        "citationCount": 50,
        "abstract": "Seed abstract.",
        "externalIds": {"DOI": "10.1000/seed-parent"},
        "openAccessPdf": {},
        "authors": [{"name": "Grace Hopper"}],
    }
    child_paper = {
        "paperId": "paper-1",
        "title": "Nutrition and metabolism",
        "year": 2024,
        "citationCount": 12,
        "abstract": "A short abstract about diet and metabolism.",
        "externalIds": {"DOI": "10.1000/demo"},
        "openAccessPdf": {"url": "https://example.org/paper.pdf"},
        "authors": [{"name": "Ada Lovelace"}],
    }

    citation_exploration.save_paper(
        child_paper,
        parent="seed-paper-1",
        parent_paper=parent_paper,
        seed_doi="10.1000/seed-parent",
        processed_papers=set(),
    )

    parent_path = citation_exploration.papers_dir / "doi-10.1000-seed-parent.metadata.json"
    child_path = citation_exploration.papers_dir / "doi-10.1000-demo.metadata.json"

    assert parent_path.exists()
    assert child_path.exists()

    saved_parent = json.loads(parent_path.read_text(encoding="utf-8"))
    saved_child = json.loads(child_path.read_text(encoding="utf-8"))

    assert saved_parent["paperId"] == "seed-paper-1"
    assert saved_parent["parent_papers"] == []
    assert saved_child["parent_papers"] == ["seed-paper-1"]


def test_save_discarded_persists_parent_metadata_when_parent_payload_is_provided(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(citation_exploration, "papers_dir", tmp_path / "metadata")
    monkeypatch.setattr(citation_exploration, "discarded_dir", tmp_path / "discarded")
    citation_exploration.papers_dir.mkdir(parents=True, exist_ok=True)
    citation_exploration.discarded_dir.mkdir(parents=True, exist_ok=True)

    parent_paper = {
        "paperId": "seed-paper-1",
        "title": "Seed parent",
        "year": 2020,
        "citationCount": 50,
        "abstract": "Seed abstract.",
        "externalIds": {"DOI": "10.1000/seed-parent"},
        "openAccessPdf": {},
        "authors": [{"name": "Grace Hopper"}],
    }
    child_paper = {
        "paperId": "paper-1",
        "title": "Nutrition and metabolism",
        "year": 2024,
        "citationCount": 12,
        "abstract": "A short abstract about diet and metabolism.",
        "externalIds": {"DOI": "10.1000/demo"},
        "openAccessPdf": {"url": "https://example.org/paper.pdf"},
        "authors": [{"name": "Ada Lovelace"}],
    }

    citation_exploration.save_discarded(
        child_paper,
        parent="seed-paper-1",
        parent_paper=parent_paper,
        seed_doi="10.1000/seed-parent",
        processed_papers=set(),
    )

    parent_path = citation_exploration.papers_dir / "doi-10.1000-seed-parent.metadata.json"
    discarded_path = citation_exploration.discarded_dir / "doi-10.1000-demo.json"

    assert parent_path.exists()
    assert discarded_path.exists()

    saved_parent = json.loads(parent_path.read_text(encoding="utf-8"))
    saved_discarded = json.loads(discarded_path.read_text(encoding="utf-8"))

    assert saved_parent["paperId"] == "seed-paper-1"
    assert saved_discarded["paperId"] == "paper-1"


def test_save_discarded_gap_rag_writes_to_dated_bucket_and_state_is_detected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(citation_exploration, "papers_dir", tmp_path / "metadata")
    monkeypatch.setattr(citation_exploration, "discarded_dir", tmp_path / "discarded")
    monkeypatch.setattr(citation_exploration, "_today_bucket_name", lambda: "2026-04-01")
    citation_exploration.papers_dir.mkdir(parents=True, exist_ok=True)
    citation_exploration.discarded_dir.mkdir(parents=True, exist_ok=True)

    paper = {
        "paperId": "paper-1",
        "title": "Unrelated mechanistic paper",
        "year": 2024,
        "citationCount": 12,
        "externalIds": {"DOI": "10.1000/demo"},
        "authors": [{"name": "Ada Lovelace"}],
    }

    citation_exploration.save_discarded(
        paper,
        seed_doi="10.1000/seed-parent",
        selection={
            "mode": "undercovered-topics",
            "decision": "drop",
            "reason": "not relevant",
            "preview": "Preview",
        },
        processed_papers=set(),
    )

    discarded_path = citation_exploration.discarded_dir / "gap-rag" / "2026-04-01" / "doi-10.1000-demo.json"
    assert discarded_path.exists()
    saved = json.loads(discarded_path.read_text(encoding="utf-8"))
    assert saved["selection"]["mode"] == "undercovered-topics"
    assert citation_exploration._paper_storage_state(paper) == "discarded"


def test_explore_with_nutrition_rag_skips_seed_not_found(monkeypatch, capsys) -> None:
    def fake_fetch(doi: str) -> dict[str, object]:
        if doi == "10.1000/missing":
            error = HTTPError("seed not found")
            error.response = SimpleNamespace(status_code=404)
            raise error
        return {
            "paperId": "paper-seed-1",
            "title": "Seed paper",
            "year": 2024,
            "citationCount": 123,
            "externalIds": {"DOI": doi},
            "openAccessPdf": {},
            "abstract": "Seed abstract",
            "authors": [{"name": "Ada Lovelace"}],
        }

    saved_seeds: list[str] = []
    completed_seeds: list[str] = []

    monkeypatch.setattr(citation_exploration, "fetch_paper_by_doi", fake_fetch)
    monkeypatch.setattr(citation_exploration, "collect_processed_papers", lambda: set())
    monkeypatch.setattr(citation_exploration, "load_completed_seed_dois", lambda doi_file=None: set())
    monkeypatch.setattr(citation_exploration, "iter_seed_citations", lambda _seed_paper: iter(()))
    monkeypatch.setattr(citation_exploration, "append_completed_seed_doi", lambda doi, doi_file=None: completed_seeds.append(doi))
    monkeypatch.setattr(
        citation_exploration,
        "save_paper",
        lambda paper, **kwargs: saved_seeds.append(str(kwargs.get("seed_doi"))),
    )

    citation_exploration.explore_with_nutrition_rag(["10.1000/missing", "10.1000/found"])

    captured = capsys.readouterr()
    assert "[SEED SKIP] 10.1000/missing -> not found in Semantic Scholar" in captured.out
    assert "- Seed DOIs skipped:      1" in captured.out
    assert saved_seeds == ["10.1000/found"]
    assert completed_seeds == ["10.1000/missing", "10.1000/found"]


def test_explore_with_nutrition_rag_skips_completed_seeds_and_processes_all_batches(monkeypatch, capsys) -> None:
    monkeypatch.setattr(citation_exploration, "selection_batch_size", 2)
    monkeypatch.setattr(citation_exploration, "load_completed_seed_dois", lambda doi_file=None: {"10.1000/done"})
    monkeypatch.setattr(citation_exploration, "collect_processed_papers", lambda: set())

    processed_batches: list[list[str]] = []
    completed_seeds: list[str] = []

    def fake_fetch(doi: str) -> dict[str, object]:
        return {
            "paperId": f"paper-{doi.rsplit('/', 1)[-1]}",
            "title": f"Seed {doi}",
            "year": 2024,
            "citationCount": 123,
            "externalIds": {"DOI": doi},
            "openAccessPdf": {},
            "abstract": "Seed abstract",
            "authors": [{"name": "Ada Lovelace"}],
        }

    def fake_iter(seed_paper: dict[str, object]):
        for index in range(5):
            yield {
                "paperId": f"{seed_paper['paperId']}-cit-{index}",
                "title": f"Citation {index}",
                "year": 2024,
                "citationCount": 150,
                "externalIds": {"DOI": f"10.1000/cit-{index}"},
                "openAccessPdf": {},
                "abstract": f"Abstract {index}",
                "authors": [{"name": "Author"}],
            }

    def fake_process(batch, accepted, *, processed_papers, selection_mode="broad-nutrition"):
        processed_batches.append([item["paper"]["paperId"] for item in batch])
        return accepted + len(batch), len(batch), len(batch), 0

    monkeypatch.setattr(citation_exploration, "fetch_paper_by_doi", fake_fetch)
    monkeypatch.setattr(citation_exploration, "iter_seed_citations", fake_iter)
    monkeypatch.setattr(citation_exploration, "_process_selection_batch", fake_process)
    monkeypatch.setattr(citation_exploration, "save_paper", lambda paper, **kwargs: None)
    monkeypatch.setattr(citation_exploration, "append_completed_seed_doi", lambda doi, doi_file=None: completed_seeds.append(doi))

    citation_exploration.explore_with_nutrition_rag(["10.1000/done", "10.1000/pending"])

    captured = capsys.readouterr()
    assert processed_batches == [
        ["paper-pending-cit-0", "paper-pending-cit-1"],
        ["paper-pending-cit-2", "paper-pending-cit-3"],
        ["paper-pending-cit-4"],
    ]
    assert completed_seeds == ["10.1000/pending"]
    assert "- Seed DOIs pending:      1" in captured.out
    assert "- Seed DOIs completed:    1" in captured.out
    assert "- Kept:                   5" in captured.out


def test_run_nutrition_rag_exploration_does_not_fail_when_first_pending_seed_is_missing(monkeypatch, capsys) -> None:
    explored: list[list[str]] = []

    monkeypatch.setattr(citation_exploration, "load_seed_dois", lambda: ["10.1000/missing", "10.1000/found"])
    monkeypatch.setattr(citation_exploration, "load_completed_seed_dois", lambda doi_file=None: set())
    monkeypatch.setattr(
        citation_exploration,
        "explore_with_nutrition_rag",
        lambda seed_dois: explored.append(list(seed_dois)),
    )

    citation_exploration.run_nutrition_rag_exploration()

    captured = capsys.readouterr()
    assert "Selection mode: broad-nutrition" in captured.out
    assert "First pending seed: 10.1000/missing" in captured.out
    assert explored == [["10.1000/missing", "10.1000/found"]]


def test_build_user_prompt_includes_title_and_preview() -> None:
    prompt = build_user_prompt(
        [
            PaperCandidate(
                id="cand_001",
                title="Diet quality and obesity",
                abstract_preview="Diet quality was associated with obesity outcomes.",
            )
        ]
    )

    assert "cand_001" in prompt
    assert "TITLE: Diet quality and obesity" in prompt
    assert "ABSTRACT_PREVIEW: Diet quality was associated with obesity outcomes." in prompt


def test_build_responses_payload_uses_gap_prompt_when_requested() -> None:
    payload = build_responses_payload(
        model="gpt-5-mini",
        candidates=[PaperCandidate(id="cand_001", title="Leucine and sarcopenia", abstract_preview="Preview")],
        selection_profile="undercovered-topics",
    )

    system_prompt = payload["input"][0]["content"]
    assert "undercovered nutrition gaps" in system_prompt
    assert "iron deficiency anemia" in system_prompt
    assert "PCOS nutrition" in system_prompt


def test_normalize_decisions_defaults_missing_candidates_to_uncertain() -> None:
    response_json = {
        "output": [
            {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "decisions": [
                                    {"id": "cand_001", "decision": "keep", "reason": "nutrition relevant"}
                                ]
                            }
                        )
                    }
                ]
            }
        ]
    }

    decisions = normalize_decisions(
        response_json,
        [
            PaperCandidate(id="cand_001", title="A", abstract_preview=""),
            PaperCandidate(id="cand_002", title="B", abstract_preview=""),
        ],
    )

    assert decisions == [
        {"id": "cand_001", "decision": "keep", "reason": "nutrition relevant"},
        {"id": "cand_002", "decision": "uncertain", "reason": "missing_from_model_output"},
    ]


def test_run_metadata_exploration_flow_routes_modes(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(metadata_stage, "run_nutrition_rag_exploration", lambda: called.append("broad-nutrition"))
    monkeypatch.setattr(metadata_stage, "run_gap_rag_exploration", lambda: called.append("undercovered-topics"))

    metadata_stage.run_metadata_exploration_flow("broad-nutrition")
    metadata_stage.run_metadata_exploration_flow("undercovered-topics")

    assert called == ["broad-nutrition", "undercovered-topics"]
