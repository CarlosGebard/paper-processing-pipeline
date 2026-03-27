from __future__ import annotations

import json

import paper_pipeline.stages.metadata as metadata_stage
import paper_pipeline.tools.citation_exploration as citation_exploration
from paper_pipeline.tools.paper_selector import PaperCandidate, build_user_prompt, normalize_decisions


def test_build_selection_preview_limits_to_twenty_words() -> None:
    text = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twentyone twentytwo"

    preview = citation_exploration.build_selection_preview(text, max_words=20)

    assert preview == "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty..."


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

    record = citation_exploration.paper_to_metadata_record(paper, parent="seed-paper", abstract_word_limit=300)

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
        "authors": ["Ada Lovelace", "Alan Turing"],
    }


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

    monkeypatch.setattr(metadata_stage, "run_interactive_exploration", lambda: called.append("interactive"))
    monkeypatch.setattr(metadata_stage, "run_nutrition_rag_exploration", lambda: called.append("nutrition-rag"))

    metadata_stage.run_metadata_exploration_flow("interactive")
    metadata_stage.run_metadata_exploration_flow("nutrition-rag")

    assert called == ["interactive", "nutrition-rag"]
