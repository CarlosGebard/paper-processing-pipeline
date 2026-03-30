from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "refilter_metadata_with_paper_selector.py"
SPEC = importlib.util.spec_from_file_location("refilter_metadata_with_paper_selector", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_load_metadata_candidate_supports_wrapped_payload(tmp_path: Path) -> None:
    metadata_path = tmp_path / "doi-10.1000-demo.metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "title": "Diet quality and obesity",
                    "abstract": "This abstract has enough words to be truncated for preview generation.",
                }
            }
        ),
        encoding="utf-8",
    )

    candidate = MODULE.load_metadata_candidate(metadata_path, preview_words=5)

    assert candidate is not None
    assert candidate.id == "doi-10.1000-demo"
    assert candidate.candidate.title == "Diet quality and obesity"
    assert candidate.candidate.abstract_preview == "This abstract has enough words..."


def test_run_refilter_dry_run_does_not_modify_metadata(tmp_path: Path, monkeypatch) -> None:
    metadata_dir = tmp_path / "metadata"
    discarded_dir = tmp_path / "discarded"
    state_file = tmp_path / "runtime" / "state.json"
    summary_file = tmp_path / "runtime" / "summary.json"
    metadata_dir.mkdir()
    kept_path = metadata_dir / "doi-10.1000-keep.metadata.json"
    drop_path = metadata_dir / "doi-10.1000-drop.metadata.json"

    kept_path.write_text(json.dumps({"title": "Keep title", "abstract": "keep abstract"}), encoding="utf-8")
    drop_path.write_text(json.dumps({"title": "Drop title", "abstract": "drop abstract"}), encoding="utf-8")

    def fake_classify(candidates, model, dotenv_path=None):
        return (
            [
                {"id": "doi-10.1000-keep", "decision": "keep", "reason": "relevant"},
                {"id": "doi-10.1000-drop", "decision": "drop", "reason": "irrelevant"},
            ],
            {"ok": True},
        )

    monkeypatch.setattr(MODULE, "classify_papers_with_openai", fake_classify)

    exit_code = MODULE.run_refilter(
        metadata_dir=metadata_dir,
        discarded_dir=discarded_dir,
        model="gpt-5-mini",
        batch_size=10,
        preview_words=10,
        limit=None,
        action="discard",
        apply_changes=False,
        state_file=state_file,
        summary_file=summary_file,
        reset_state=True,
    )

    assert exit_code == 0
    assert kept_path.exists()
    assert drop_path.exists()
    assert not discarded_dir.exists()
    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    summary_payload = json.loads(summary_file.read_text(encoding="utf-8"))
    assert state_payload["reviewed_count"] == 2
    assert summary_payload["newly_rejected_count"] == 1


def test_run_refilter_discard_action_writes_record_and_removes_metadata(tmp_path: Path, monkeypatch) -> None:
    metadata_dir = tmp_path / "metadata"
    discarded_dir = tmp_path / "discarded"
    state_file = tmp_path / "runtime" / "state.json"
    summary_file = tmp_path / "runtime" / "summary.json"
    metadata_dir.mkdir()
    keep_path = metadata_dir / "doi-10.1000-keep.metadata.json"
    drop_path = metadata_dir / "doi-10.1000-drop.metadata.json"
    uncertain_path = metadata_dir / "doi-10.1000-uncertain.metadata.json"

    keep_path.write_text(json.dumps({"title": "Keep", "doi": "10.1000/keep"}), encoding="utf-8")
    drop_path.write_text(
        json.dumps({"title": "Drop", "doi": "10.1000/drop", "paperId": "paper-drop", "authors": ["Ada"]}),
        encoding="utf-8",
    )
    uncertain_path.write_text(json.dumps({"title": "Uncertain", "doi": "10.1000/uncertain"}), encoding="utf-8")

    def fake_classify(candidates, model, dotenv_path=None):
        return (
            [
                {"id": "doi-10.1000-keep", "decision": "keep", "reason": "in scope"},
                {"id": "doi-10.1000-drop", "decision": "drop", "reason": "not nutrition"},
                {"id": "doi-10.1000-uncertain", "decision": "uncertain", "reason": "not enough signal"},
            ],
            {"ok": True},
        )

    monkeypatch.setattr(MODULE, "classify_papers_with_openai", fake_classify)

    exit_code = MODULE.run_refilter(
        metadata_dir=metadata_dir,
        discarded_dir=discarded_dir,
        model="gpt-5-mini",
        batch_size=10,
        preview_words=10,
        limit=None,
        action="discard",
        apply_changes=True,
        state_file=state_file,
        summary_file=summary_file,
        reset_state=True,
    )

    discarded_file = discarded_dir / "doi-10.1000-drop.json"

    assert exit_code == 0
    assert keep_path.exists()
    assert not drop_path.exists()
    assert uncertain_path.exists()
    assert discarded_file.exists()

    discarded_payload = json.loads(discarded_file.read_text(encoding="utf-8"))
    assert discarded_payload["paperId"] == "paper-drop"
    assert discarded_payload["doi"] == "10.1000/drop"
    assert discarded_payload["selection"] == {
        "decision": "drop",
        "reason": "not nutrition",
        "source": "refilter_metadata_with_paper_selector",
    }
    assert discarded_payload["source_metadata_file"] == "doi-10.1000-drop.metadata.json"
    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    summary_payload = json.loads(summary_file.read_text(encoding="utf-8"))
    assert state_payload["completed"] is True
    assert state_payload["reviewed_count"] == 3
    assert summary_payload["newly_rejected_count"] == 1
    assert summary_payload["newly_rejected"][0]["discarded_path"].endswith("doi-10.1000-drop.json")


def test_run_refilter_resumes_from_existing_state(tmp_path: Path, monkeypatch) -> None:
    metadata_dir = tmp_path / "metadata"
    discarded_dir = tmp_path / "discarded"
    state_file = tmp_path / "runtime" / "state.json"
    summary_file = tmp_path / "runtime" / "summary.json"
    metadata_dir.mkdir()
    first_path = metadata_dir / "doi-10.1000-first.metadata.json"
    second_path = metadata_dir / "doi-10.1000-second.metadata.json"

    first_path.write_text(json.dumps({"title": "First", "doi": "10.1000/first"}), encoding="utf-8")
    second_path.write_text(json.dumps({"title": "Second", "doi": "10.1000/second"}), encoding="utf-8")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "completed": False,
                "reviewed_count": 1,
                "kept_count": 1,
                "dropped_count": 0,
                "uncertain_count": 0,
                "invalid_count": 0,
                "processed_ids": ["doi-10.1000-first"],
                "newly_rejected": [],
            }
        ),
        encoding="utf-8",
    )

    observed_batches: list[list[str]] = []

    def fake_classify(candidates, model, dotenv_path=None):
        observed_batches.append([candidate.id for candidate in candidates])
        return (
            [
                {"id": "doi-10.1000-second", "decision": "drop", "reason": "reject second"},
            ],
            {"ok": True},
        )

    monkeypatch.setattr(MODULE, "classify_papers_with_openai", fake_classify)

    exit_code = MODULE.run_refilter(
        metadata_dir=metadata_dir,
        discarded_dir=discarded_dir,
        model="gpt-5-mini",
        batch_size=10,
        preview_words=10,
        limit=None,
        action="discard",
        apply_changes=True,
        state_file=state_file,
        summary_file=summary_file,
        reset_state=False,
    )

    state_payload = json.loads(state_file.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert observed_batches == [["doi-10.1000-second"]]
    assert first_path.exists()
    assert not second_path.exists()
    assert state_payload["reviewed_count"] == 2
    assert state_payload["dropped_count"] == 1
