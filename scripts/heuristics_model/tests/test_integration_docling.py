from pathlib import Path

from heuristics_model.chunking import build_chunks
from heuristics_model.pipeline import process_markdown


def test_integration_docling_markdown_preserves_main_sections() -> None:
    markdown_path = Path(__file__).resolve().parents[1] / "input_markdown" / "markdown_example.md"
    text = markdown_path.read_text(encoding="utf-8")

    structure = process_markdown(text)
    section_names = [section.title for section in structure.sections]

    assert "introduction" in section_names
    assert "methods" in section_names
    assert "results" in section_names
    assert "discussion" in section_names

    chunks = build_chunks(structure)
    methods_chunks = [c for c in chunks if c["section"] == "methods"]
    results_chunks = [c for c in chunks if c["section"] == "results"]
    discussion_chunks = [c for c in chunks if c["section"] == "discussion"]

    assert methods_chunks
    assert results_chunks
    assert discussion_chunks
