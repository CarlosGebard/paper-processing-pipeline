from __future__ import annotations

from pathlib import Path

from src import config as ctx
from src.stages.processing import resolve_pdf_for_doi, run_single_paper_testing_flow


def test_resolve_pdf_for_doi_prefers_canonical_name(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    canonical = input_dir / "doi-10.1000-demo.pdf"
    canonical.write_bytes(b"%PDF-1.4\n")
    (input_dir / "DOC1__doi-10.1000-demo.pdf").write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(ctx, "DOCLING_INPUT_DIR", input_dir)

    resolved = resolve_pdf_for_doi("10.1000/demo")

    assert resolved == canonical


def test_run_single_paper_testing_flow_writes_to_testing_dirs(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    metadata_dir = tmp_path / "metadata"
    testing_docling_dir = tmp_path / "testing" / "docling"
    testing_claims_dir = tmp_path / "testing" / "claims"
    root_dir = tmp_path / "root"

    for directory in (input_dir, metadata_dir, testing_docling_dir, testing_claims_dir):
        directory.mkdir(parents=True, exist_ok=True)

    pdf_path = input_dir / "doi-10.1000-demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    final_json = testing_docling_dir / "doi-10.1000-demo" / "doi-10.1000-demo.final.json"
    final_json.parent.mkdir(parents=True, exist_ok=True)
    final_json.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ctx, "DOCLING_INPUT_DIR", input_dir)
    monkeypatch.setattr(ctx, "METADATA_DIR", metadata_dir)
    monkeypatch.setattr(ctx, "TESTING_DOCLING_DIR", testing_docling_dir)
    monkeypatch.setattr(ctx, "TESTING_CLAIMS_DIR", testing_claims_dir)
    monkeypatch.setattr(ctx, "ROOT_DIR", root_dir)

    monkeypatch.setattr(
        "src.stages.processing.parse_document_from_pdf_name",
        lambda path: ("DOC123", "10.1000/demo", "doi-10.1000-demo"),
    )

    def fake_runner(**kwargs: object) -> dict[str, object]:
        assert kwargs["input_pdf"] == pdf_path
        assert kwargs["output_root_dir"] == testing_docling_dir
        return {
            "output_dir": testing_docling_dir / "doi-10.1000-demo",
            "json_path": testing_docling_dir / "doi-10.1000-demo" / "doi-10.1000-demo.json",
            "filtered_json_path": testing_docling_dir / "doi-10.1000-demo" / "doi-10.1000-demo.filtered.json",
            "final_json_path": final_json,
        }

    def fake_claims_flow(
        input_path: Path,
        output_path: Path,
        model: str,
        max_claims: int | None,
        temperature: float,
        pattern: str,
    ) -> tuple[int, int, int]:
        assert input_path == final_json
        assert output_path == testing_claims_dir
        assert model == ctx.LLM_CLAIMS_MODEL
        assert max_claims is None
        assert temperature == ctx.LLM_CLAIMS_TEMPERATURE
        assert pattern == "*/*.final.json"
        return (1, 0, 0)

    monkeypatch.setattr(ctx, "resolve_docling_v2_pipeline_runner", lambda: fake_runner)
    monkeypatch.setattr(ctx, "resolve_claims_flow", lambda: fake_claims_flow)

    result = run_single_paper_testing_flow("10.1000/demo")

    assert result["final_json_path"] == final_json
    assert result["claims_path"] == testing_claims_dir / "doi-10.1000-demo.claims.json"
    assert result["claims_processed"] == 1
