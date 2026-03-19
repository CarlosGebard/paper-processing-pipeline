from heuristics_model.pipeline import process_markdown
from heuristics_model.rendering import render_markdown


def test_render_markdown_reconstructs_hierarchy() -> None:
    text = """
## Methods
Methods intro
### Statistical Analysis
Stats details
"""
    structure = process_markdown(text)
    out = render_markdown(structure)
    assert "# Methods" in out
    assert "## Statistical Analysis" in out
    assert "Stats details" in out
