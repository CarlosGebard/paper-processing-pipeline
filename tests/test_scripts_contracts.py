from __future__ import annotations

import json
from pathlib import Path

from src import artifacts
import src.tools.claims_extraction as claims_extraction
from src.tools.bibliography import generate_bib
from src.tools.claims_extraction import (
    AUTO_APPROVE_MAX_TOKENS,
    build_claims_preview,
    build_prompt,
    compute_dynamic_claim_limit,
    derive_output_file,
    parse_input_sections,
    run_claim_extraction_flow,
    run_claim_extraction_for_file,
)
from src.tools.pdf_normalization import (
    _guess_base_name_from_stem,
    audit_raw_pdf_dir,
    sync_raw_pdfs_into_input,
)


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
    assert (input_dir / "doi-10.1000-demo.pdf").exists()


def test_guess_base_name_handles_truncated_author_year_filename() -> None:
    metadata_records = [
        {
            "document_id": "DOC999",
            "doi": "10.1000/demo",
            "title_key": "effectofsleepextensiononobjectivelyassessedenergyintakeamongadultswithoverweightinreallifesettings",
            "base_name": "doi-10.1000-demo",
        }
    ]

    guessed = _guess_base_name_from_stem(
        "Tasali et al. - 2022 - Effect of sleep extension on objectively assessed energy intake among adults with overweight in real",
        metadata_records,
        [],
    )

    assert guessed == "doi-10.1000-demo"


def test_audit_raw_pdf_dir_reports_resolution_buckets(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    metadata_dir = tmp_path / "metadata"

    raw_dir.mkdir()
    metadata_dir.mkdir()

    (raw_dir / "doi-10.1000-known.pdf").write_bytes(b"%PDF-1.4\n")
    (raw_dir / "DOC1__doi-10.1000-legacy.pdf").write_bytes(b"%PDF-1.4\n")
    (raw_dir / "Example Paper.pdf").write_bytes(b"%PDF-1.4\n")
    (raw_dir / "Unknown Paper.pdf").write_bytes(b"%PDF-1.4\n")

    metadata = {
        "metadata": {
            "document_id": "DOC123",
            "doi": "10.1000/demo",
            "title": "Example Paper",
        }
    }
    (metadata_dir / "record.json").write_text(json.dumps(metadata), encoding="utf-8")

    summary = audit_raw_pdf_dir(raw_dir, metadata_dir)

    assert summary["total"] == 4
    assert summary["already_doi"] == 1
    assert summary["legacy"] == 1
    assert summary["matched_from_lookup"] == 1
    assert summary["unmatched"] == 1
    assert summary["unmatched_files"] == ["Unknown Paper.pdf"]


def test_sync_raw_pdfs_uses_doi_pdf_relations_as_fallback(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    input_dir = tmp_path / "input"
    metadata_dir = tmp_path / "metadata"
    relations_csv = tmp_path / "doi_pdf_relations_demo.csv"

    raw_dir.mkdir()
    metadata_dir.mkdir()

    source_pdf = raw_dir / "Example Paper.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n")

    relations_csv.write_text(
        (
            "collection_name,parent_item_id,parent_key,doi,attachment_item_id,attachment_key,content_type,"
            "attachment_path_raw,resolved_pdf_path\n"
            "Demo,1,AAA,10.1000/demo,2,BBB,application/pdf,"
            "\"storage:Example Paper.pdf\",\"storage/BBB/Example Paper.pdf\"\n"
        ),
        encoding="utf-8",
    )

    copied, skipped = sync_raw_pdfs_into_input(
        raw_dir,
        input_dir,
        metadata_dir,
        bib_file=None,
        relations_csv=relations_csv,
    )

    assert copied == 1
    assert skipped == 0
    assert (input_dir / "doi-10.1000-demo.pdf").exists()


def test_guess_base_name_prefers_highest_citation_metadata_when_title_is_ambiguous() -> None:
    metadata_records = [
        {
            "document_id": "DOC1",
            "doi": "10.2337/dc13-2042",
            "title_key": "nutritiontherapyrecommendationsforthemanagementofadultswithdiabetes",
            "base_name": "doi-10.2337-dc13-2042",
            "citation_count": "541",
        },
        {
            "document_id": "DOC2",
            "doi": "10.2337/dc14-s120",
            "title_key": "nutritiontherapyrecommendationsforthemanagementofadultswithdiabetes",
            "base_name": "doi-10.2337-dc14-s120",
            "citation_count": "854",
        },
    ]
    relation_records = [
        {
            "title_key": "nutritiontherapyrecommendationsforthemanagementofadultswithdiabetes",
            "doi": "10.2337/dc13-2042",
            "base_name": "doi-10.2337-dc13-2042",
        },
        {
            "title_key": "nutritiontherapyrecommendationsforthemanagementofadultswithdiabetes",
            "doi": "10.2337/dc14-s120",
            "base_name": "doi-10.2337-dc14-s120",
        },
    ]

    guessed = _guess_base_name_from_stem(
        "Evert et al. - 2013 - Nutrition therapy recommendations for the management of adults with diabetes",
        metadata_records,
        [],
        relation_records,
    )

    assert guessed == "doi-10.2337-dc14-s120"


def test_parse_input_sections_reads_json_heuristics_output(tmp_path: Path) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    payload = {
        "paper": {"title": "Example paper"},
        "sections": [
            {"title": "Abstract", "text": "Abstract body.", "subsections": []},
            {
                "title": "Methods",
                "text": "Methods body.",
                "subsections": [{"title": "Design", "text": "Randomized trial.", "subsections": []}],
            },
            {"title": "Results", "text": "Results body.", "subsections": []},
        ],
    }
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    sections = parse_input_sections(input_file)

    assert sections["trace"] == ""
    assert sections["available_sections"] == ["Abstract", "Methods", "Results"]
    assert "## Abstract\nAbstract body." in sections["sections_text"]
    assert "## Methods\nMethods body." in sections["sections_text"]
    assert "Design\nRandomized trial." in sections["sections_text"]
    assert "## Results\nResults body." in sections["sections_text"]


def test_parse_input_sections_uses_top_level_final_sections(tmp_path: Path) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    payload = {
        "sections": [
            {"title": "Abstract", "text": "Final abstract.", "subsections": []},
            {"title": "Methods", "text": "Final methods.", "subsections": []},
            {"title": "Results", "text": "Final results.", "subsections": []},
        ],
        "filtered": {
            "sections": [
                {"title": "Abstract", "text": "Filtered abstract.", "subsections": []},
                {"title": "Methods", "text": "Filtered methods.", "subsections": []},
                {"title": "Results", "text": "Filtered results.", "subsections": []},
            ]
        },
    }
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    sections = parse_input_sections(input_file)

    assert sections["available_sections"] == ["Abstract", "Methods", "Results"]
    assert "Final abstract." in sections["sections_text"]
    assert "Final methods." in sections["sections_text"]
    assert "Final results." in sections["sections_text"]
    assert "Filtered abstract." not in sections["sections_text"]


def test_build_claims_preview_uses_top_level_paper_title(tmp_path: Path) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    input_file.write_text(
        json.dumps(
            {
                "paper_title": "Example preview title",
                "sections": [{"title": "Results", "text": "Result body.", "subsections": []}],
            }
        ),
        encoding="utf-8",
    )

    preview = build_claims_preview(input_file, max_claims=10)

    assert preview["title"] == "Example preview title"


def test_parse_input_sections_rejects_markdown_inputs(tmp_path: Path) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.md"
    input_file.write_text("# Results\nExample", encoding="utf-8")

    try:
        parse_input_sections(input_file)
    except ValueError as exc:
        assert "solo soporta archivos JSON final" in str(exc)
    else:
        raise AssertionError("Expected ValueError for markdown input")


def test_derive_output_file_supports_json_inputs(tmp_path: Path) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    output_dir = tmp_path / "claims"

    derived = derive_output_file(input_file, output_dir)

    assert derived == output_dir / "doi-10.1000-demo.claims.json"


def test_build_claims_preview_reports_title_sections_and_tokens(tmp_path: Path) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    payload = {
        "paper": {"title": "Example paper", "citation_count": 250},
        "sections": [
            {"title": "Abstract", "text": "Abstract body.", "subsections": []},
            {"title": "Results", "text": "Results body.", "subsections": []},
        ],
    }
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    preview = build_claims_preview(input_file, max_claims=None)

    assert preview["title"] == "Example paper"
    assert preview["section_count"] == 2
    assert preview["estimated_input_tokens"] > 0
    assert preview["claims_limit"]["final_claims"] >= 10


def test_compute_dynamic_claim_limit_weights_text_more_than_citations() -> None:
    low_text = compute_dynamic_claim_limit(citation_count=1000, word_count=1500)
    high_text = compute_dynamic_claim_limit(citation_count=100, word_count=12000)

    assert low_text["final_claims"] >= 10
    assert high_text["final_claims"] > low_text["final_claims"]
    assert high_text["extra_claims"] > 0


def test_run_claim_extraction_flow_overwrites_existing_claims(tmp_path: Path, monkeypatch) -> None:
    input_root = tmp_path / "03_docling_heuristics"
    paper_dir = input_root / "doi-10.1000-demo"
    input_file = paper_dir / "doi-10.1000-demo.final.json"
    output_dir = tmp_path / "04_claims"
    output_file = output_dir / "doi-10.1000-demo.claims.json"

    paper_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_file.write_text(json.dumps({"sections": []}), encoding="utf-8")
    output_file.write_text("old", encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class DummyOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    def fake_run_claim_extraction_for_file(
        client: object,
        input_path: Path,
        output_path: Path,
        model: str,
        max_claims: int,
        temperature: float,
    ) -> int:
        assert isinstance(client, DummyOpenAI)
        assert input_path == input_file
        assert output_path == output_file
        output_path.write_text(json.dumps([{"claim_text": "new"}]), encoding="utf-8")
        return 1

    monkeypatch.setattr(claims_extraction, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(claims_extraction, "run_claim_extraction_for_file", fake_run_claim_extraction_for_file)

    processed, overwritten, failed = run_claim_extraction_flow(
        input_path=input_root,
        output=output_dir,
        model="gpt-5-mini",
        max_claims=10,
        temperature=0.0,
    )

    assert processed == 1
    assert overwritten == 1
    assert failed == 0
    assert json.loads(output_file.read_text(encoding="utf-8")) == [{"claim_text": "new"}]


def test_run_claim_extraction_flow_defers_review_callback_skip_until_final_pass(tmp_path: Path, monkeypatch) -> None:
    input_root = tmp_path / "03_docling_heuristics"
    paper_dir = input_root / "doi-10.1000-demo"
    input_file = paper_dir / "doi-10.1000-demo.final.json"
    output_dir = tmp_path / "04_claims"

    paper_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_file.write_text(
        json.dumps(
            {
                "paper": {"title": "Example paper"},
                "sections": [{"title": "Abstract", "text": "Abstract body.", "subsections": []}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class DummyOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    called = {"ran": False}

    def fake_run_claim_extraction_for_file(**_: object) -> int:
        called["ran"] = True
        return 1

    monkeypatch.setattr(claims_extraction, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(claims_extraction, "run_claim_extraction_for_file", fake_run_claim_extraction_for_file)

    callback_calls = {"count": 0}

    def review_callback(file_path: Path, preview: dict[str, object], output_path: Path) -> bool:
        callback_calls["count"] += 1
        if callback_calls["count"] == 1:
            assert preview["review_phase"] == "initial"
            return False
        assert preview["review_phase"] == "final"
        return False

    processed, overwritten, failed = run_claim_extraction_flow(
        input_path=input_root,
        output=output_dir,
        model="gpt-5-mini",
        max_claims=10,
        temperature=0.0,
        review_callback=review_callback,
    )

    assert processed == 0
    assert overwritten == 0
    assert failed == 0
    assert called["ran"] is False
    assert callback_calls["count"] == 2


def test_run_claim_extraction_flow_processes_deferred_file_on_final_pass(tmp_path: Path, monkeypatch) -> None:
    input_root = tmp_path / "03_docling_heuristics"
    paper_dir = input_root / "doi-10.1000-demo"
    input_file = paper_dir / "doi-10.1000-demo.final.json"
    output_dir = tmp_path / "04_claims"

    paper_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_file.write_text(
        json.dumps(
            {
                "paper": {"title": "Example paper"},
                "sections": [{"title": "Abstract", "text": "Abstract body.", "subsections": []}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class DummyOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    callback_calls = {"count": 0}
    called = {"ran": False}

    def review_callback(file_path: Path, preview: dict[str, object], output_path: Path) -> bool:
        callback_calls["count"] += 1
        return callback_calls["count"] == 2

    def fake_run_claim_extraction_for_file(**_: object) -> int:
        called["ran"] = True
        return 1

    monkeypatch.setattr(claims_extraction, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(claims_extraction, "run_claim_extraction_for_file", fake_run_claim_extraction_for_file)

    processed, overwritten, failed = run_claim_extraction_flow(
        input_path=input_root,
        output=output_dir,
        model="gpt-5-mini",
        max_claims=10,
        temperature=0.0,
        review_callback=review_callback,
    )

    assert processed == 1
    assert overwritten == 0
    assert failed == 0
    assert called["ran"] is True
    assert callback_calls["count"] == 2


def test_run_claim_extraction_flow_auto_approves_under_token_threshold(tmp_path: Path, monkeypatch) -> None:
    input_root = tmp_path / "03_docling_heuristics"
    paper_dir = input_root / "doi-10.1000-demo"
    input_file = paper_dir / "doi-10.1000-demo.final.json"
    output_dir = tmp_path / "04_claims"

    paper_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_file.write_text(
        json.dumps(
            {
                "paper": {"title": "Example paper"},
                "sections": [{"title": "Abstract", "text": "short body", "subsections": []}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class DummyOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    called = {"ran": False}

    def fake_run_claim_extraction_for_file(**_: object) -> int:
        called["ran"] = True
        return 1

    monkeypatch.setattr(claims_extraction, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(claims_extraction, "run_claim_extraction_for_file", fake_run_claim_extraction_for_file)

    processed, overwritten, failed = run_claim_extraction_flow(
        input_path=input_root,
        output=output_dir,
        model="gpt-5-mini",
        max_claims=10,
        temperature=0.0,
        auto_approve_max_tokens=AUTO_APPROVE_MAX_TOKENS,
    )

    assert processed == 1
    assert overwritten == 0
    assert failed == 0
    assert called["ran"] is True


def test_run_claim_extraction_flow_skip_existing_runs_before_preview(tmp_path: Path, monkeypatch) -> None:
    input_root = tmp_path / "03_docling_heuristics"
    paper_dir = input_root / "doi-10.1000-demo"
    input_file = paper_dir / "doi-10.1000-demo.final.json"
    output_dir = tmp_path / "04_claims"
    output_file = output_dir / "doi-10.1000-demo.claims.json"

    paper_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_file.write_text(json.dumps({"sections": []}), encoding="utf-8")
    output_file.write_text("[]", encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class DummyOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    def fail_preview(*_: object, **__: object) -> dict[str, object]:
        raise AssertionError("build_claims_preview should not run when skip_existing is enabled")

    def fail_run(*_: object, **__: object) -> int:
        raise AssertionError("run_claim_extraction_for_file should not run when output already exists")

    monkeypatch.setattr(claims_extraction, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(claims_extraction, "build_claims_preview", fail_preview)
    monkeypatch.setattr(claims_extraction, "run_claim_extraction_for_file", fail_run)

    processed, overwritten, failed = run_claim_extraction_flow(
        input_path=input_root,
        output=output_dir,
        model="gpt-5-mini",
        max_claims=10,
        temperature=0.0,
        skip_existing=True,
    )

    assert processed == 0
    assert overwritten == 0
    assert failed == 0


def test_run_claim_extraction_flow_skips_auto_mode_at_or_above_threshold(tmp_path: Path, monkeypatch) -> None:
    input_root = tmp_path / "03_docling_heuristics"
    paper_dir = input_root / "doi-10.1000-demo"
    input_file = paper_dir / "doi-10.1000-demo.final.json"
    output_dir = tmp_path / "04_claims"
    long_text = " ".join(["result"] * 30000)

    paper_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_file.write_text(
        json.dumps(
            {
                "paper": {"title": "Example paper"},
                "sections": [{"title": "Results", "text": long_text, "subsections": []}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class DummyOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    called = {"ran": False}

    def fake_run_claim_extraction_for_file(**_: object) -> int:
        called["ran"] = True
        return 1

    monkeypatch.setattr(claims_extraction, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(claims_extraction, "run_claim_extraction_for_file", fake_run_claim_extraction_for_file)

    processed, overwritten, failed = run_claim_extraction_flow(
        input_path=input_root,
        output=output_dir,
        model="gpt-5-mini",
        max_claims=10,
        temperature=0.0,
        auto_approve_max_tokens=AUTO_APPROVE_MAX_TOKENS,
    )

    assert processed == 0
    assert overwritten == 0
    assert failed == 0
    assert called["ran"] is False


def test_run_claim_extraction_for_file_inserts_all_sections_into_prompt(tmp_path: Path) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    output_file = tmp_path / "doi-10.1000-demo.claims.json"
    input_file.write_text(
        json.dumps(
            {
                "sections": [
                    {"title": "Dietary Patterns", "text": "First section body.", "subsections": []},
                    {"title": "2. Mediterranean Diet", "text": "Second section body.", "subsections": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class DummyResponses:
        def create(self, *, model: str, input: list[dict[str, object]]) -> object:
            captured["model"] = model
            captured["input"] = input

            class Response:
                output_text = "[]"

            return Response()

    class DummyClient:
        responses = DummyResponses()

    processed = run_claim_extraction_for_file(
        client=DummyClient(),
        input_path=input_file,
        output_path=output_file,
        model="gpt-5-mini",
        max_claims=10,
        temperature=0.0,
    )

    assert processed == 0
    prompt = captured["input"][0]["content"][0]["text"]  # type: ignore[index]
    assert "AVAILABLE_SECTIONS = Dietary Patterns, 2. Mediterranean Diet" in prompt
    assert "[SECTIONS]" in prompt
    assert "## Dietary Patterns\nFirst section body." in prompt
    assert "## 2. Mediterranean Diet\nSecond section body." in prompt
    assert output_file.exists()
    assert json.loads(output_file.read_text(encoding="utf-8")) == []


def test_run_claim_extraction_for_file_uses_dynamic_claim_limit(tmp_path: Path, monkeypatch) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    output_file = tmp_path / "doi-10.1000-demo.claims.json"
    long_text = " ".join(["result"] * 12000)
    input_file.write_text(
        json.dumps(
            {
                "paper": {"paper_id": "DOC123", "doi": "10.1000/demo", "citation_count": 800},
                "sections": [{"title": "Results", "text": long_text, "subsections": []}],
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class DummyResponses:
        def create(self, *, model: str, input: list[dict[str, object]]) -> object:
            captured["input"] = input

            class Response:
                output_text = "[]"

            return Response()

    class DummyClient:
        responses = DummyResponses()

    monkeypatch.setattr(claims_extraction, "record_claims_run", lambda **_: {})

    processed = run_claim_extraction_for_file(
        client=DummyClient(),
        input_path=input_file,
        output_path=output_file,
        model="gpt-5-mini",
        max_claims=None,
        temperature=0.0,
    )

    assert processed == 0
    prompt = captured["input"][0]["content"][0]["text"]  # type: ignore[index]
    assert "MAX_CLAIMS = 18" in prompt


def test_run_claim_extraction_for_file_respects_fixed_override(tmp_path: Path, monkeypatch) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    output_file = tmp_path / "doi-10.1000-demo.claims.json"
    input_file.write_text(
        json.dumps(
            {
                "paper": {"paper_id": "DOC123", "doi": "10.1000/demo", "citation_count": 800},
                "sections": [{"title": "Results", "text": "short text", "subsections": []}],
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class DummyResponses:
        def create(self, *, model: str, input: list[dict[str, object]]) -> object:
            captured["input"] = input

            class Response:
                output_text = "[]"

            return Response()

    class DummyClient:
        responses = DummyResponses()

    monkeypatch.setattr(claims_extraction, "record_claims_run", lambda **_: {})

    processed = run_claim_extraction_for_file(
        client=DummyClient(),
        input_path=input_file,
        output_path=output_file,
        model="gpt-5-mini",
        max_claims=12,
        temperature=0.0,
    )

    assert processed == 0
    prompt = captured["input"][0]["content"][0]["text"]  # type: ignore[index]
    assert "MAX_CLAIMS = 12" in prompt


def test_build_prompt_renders_full_prompt_from_final_json_sections(tmp_path: Path) -> None:
    input_file = tmp_path / "doi-10.1000-demo.final.json"
    input_file.write_text(
        json.dumps(
            {
                "trace": {"document_id": "DOC123", "doi": "10.1000/demo"},
                "sections": [
                    {"title": "Dietary Patterns", "text": "First section body.", "subsections": []},
                    {
                        "title": "2. Mediterranean Diet",
                        "text": "Second section body.",
                        "subsections": [{"title": "Evidence", "text": "Nested evidence.", "subsections": []}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    sections = parse_input_sections(input_file)
    prompt = build_prompt(
        trace_text=sections["trace"],
        sections_text=sections["sections_text"],
        max_claims=10,
        available_sections=", ".join(sections["available_sections"]),
    )

    assert "AVAILABLE_SECTIONS = Dietary Patterns, 2. Mediterranean Diet" in prompt
    assert '[TRACE]\n{\n  "document_id": "DOC123",' in prompt
    assert "[SECTIONS]" in prompt
    assert "## Dietary Patterns\nFirst section body." in prompt
    assert "## 2. Mediterranean Diet\nSecond section body." in prompt
    assert "Evidence\nNested evidence." in prompt


def test_parse_document_from_pdf_name_supports_doi_first_and_legacy(tmp_path: Path, monkeypatch) -> None:
    metadata_dir = tmp_path / "metadata"
    registry_file = tmp_path / "artifact_registry.jsonl"
    metadata_dir.mkdir()

    metadata = {
        "metadata": {
            "document_id": "DOC123",
            "doi": "10.1000/demo",
            "title": "Example Paper",
        }
    }
    (metadata_dir / "doi-10.1000-demo.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    monkeypatch.setattr(artifacts.ctx, "METADATA_DIR", metadata_dir)
    monkeypatch.setattr(artifacts.ctx, "REGISTRY_FILE", registry_file)

    doi_first = artifacts.parse_document_from_pdf_name(tmp_path / "doi-10.1000-demo.pdf")
    legacy = artifacts.parse_document_from_pdf_name(tmp_path / "DOC123__doi-10.1000-demo.pdf")

    assert doi_first == ("DOC123", "10.1000/demo", "doi-10.1000-demo")
    assert legacy == ("DOC123", "10.1000/demo", "doi-10.1000-demo")
