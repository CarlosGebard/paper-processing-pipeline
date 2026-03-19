from heuristics_model.chunking import build_chunks
from heuristics_model.pipeline import process_markdown


def test_pipeline_cuts_on_references() -> None:
    text = """
## Introduction
Intro text
## Methods
Methods text
## References
Ref block
## Discussion
Should never be processed
"""
    out = process_markdown(text)
    names = [s.title for s in out.sections]
    assert "introduction" in names
    assert "methods" in names
    assert "discussion" not in names


def test_pipeline_merges_repeated_sections() -> None:
    text = """
## Results
First block
## Methods
M block
## Results
Second block
"""
    out = process_markdown(text)
    results = [s for s in out.sections if s.title == "results"]
    assert len(results) == 1
    assert len(results[0].content) == 2


def test_pipeline_stacks_subsections_under_active_section() -> None:
    text = """
## Methods
Methods intro
### Statistical Analysis
Stats details
### Outcomes
Outcome details
## Results
Result text
"""
    out = process_markdown(text)
    methods = next(s for s in out.sections if s.title == "methods")
    subsection_titles = [sub.title for sub in methods.subsections]
    assert "statistical analysis" in subsection_titles
    assert "outcomes" in subsection_titles


def test_pipeline_filters_caption_noise() -> None:
    text = """
## Results
Figure 1 Participant flow
Useful interpretation line.
"""
    out = process_markdown(text)
    results = next(s for s in out.sections if s.title == "results")
    merged_text = "\n".join(node.text for node in results.content)
    assert "Figure 1" not in merged_text
    assert "Useful interpretation line." in merged_text


def test_chunking_includes_source_spans() -> None:
    text = """
## Methods
Methods text
### Statistical Analysis
Stats text
"""
    structure = process_markdown(text)
    chunks = build_chunks(structure)
    assert chunks
    assert all("source_span" in chunk for chunk in chunks)
    assert all(":" in chunk["source_span"] for chunk in chunks)


def test_methods_results_discussion_preserved() -> None:
    text = """
## Introduction
Intro
## Materials and Methods
Method content
## Results and Discussion
Joint content
## Conclusions
Done
"""
    out = process_markdown(text)
    names = [s.title for s in out.sections]
    assert "introduction" in names
    assert "methods" in names
    assert "results_discussion" in names
    assert "conclusion" in names


def test_pipeline_skips_markdown_tables_and_tracks_metadata() -> None:
    text = """
## Results
Narrative intro
| col1 | col2 |
| --- | --- |
| a | b |
Narrative outro
"""
    out = process_markdown(text)
    results = next(s for s in out.sections if s.title == "results")
    merged_text = "\n".join(node.text for node in results.content)
    assert "| col1 | col2 |" not in merged_text
    assert "Narrative intro" in merged_text
    assert "Narrative outro" in merged_text
    assert out.ignored_tables


def test_pipeline_reorders_sections_to_canonical_order() -> None:
    text = """
## Discussion
Discussion text
## Introduction
Intro text
## Methods
Method text
## Results
Results text
# Strange Section
Other
"""
    out = process_markdown(text)
    names = [s.title for s in out.sections]
    assert names.index("introduction") < names.index("methods")
    assert names.index("methods") < names.index("results")
    assert names.index("results") < names.index("discussion")
    assert names.index("strange section") < len(names)


def test_results_subsections_same_level_do_not_fall_into_unclassified() -> None:
    text = """
## Results
Short interrupted results text.
## Results
## Description of studies
Detailed results body.
## Effects of long chain omega-3
More detailed outcomes.
"""
    out = process_markdown(text)
    results = next(s for s in out.sections if s.title == "results")
    result_subsections = [sub.title for sub in results.subsections]

    assert "description of studies" in result_subsections
    assert "effects of long chain omega-3" in result_subsections
    assert not any(s.title == "unclassified" and s.subsections for s in out.sections)


def test_pipeline_skips_editorial_subsections() -> None:
    text = """
## Results
Main outcomes.
## What This Study Adds
Editorial summary that should be skipped.
## Discussion
Interpretation.
"""
    out = process_markdown(text)
    results = next(s for s in out.sections if s.title == "results")
    assert not results.subsections
    assert results.content


def test_pipeline_skips_editorial_metadata_and_reference_lists_in_text() -> None:
    text = """
## Discussion
Interpretation paragraph.

Funding: Supported by grant ABC.
Competing interests: None declared.

- 1 World Health Organization. Example report.
- 2 Doe J. Example trial.
- 3 Smith A. Example review.
"""
    out = process_markdown(text)
    discussion = next(s for s in out.sections if s.title == "discussion")
    merged_text = "\n".join(node.text for node in discussion.content)
    assert "Interpretation paragraph." in merged_text
    assert "Funding:" not in merged_text
    assert "Competing interests:" not in merged_text
    assert "World Health Organization" not in merged_text


def test_pipeline_skips_editorial_heading_by_prefix() -> None:
    text = """
## Discussion
Interpretation paragraph.
## Cite This As: Bmj 2019;366:L4697
https://doi.org/10.1136/bmj.l4697
"""
    out = process_markdown(text)
    discussion = next(s for s in out.sections if s.title == "discussion")
    merged_text = "\n".join(node.text for node in discussion.content)
    assert "Interpretation paragraph." in merged_text
    assert "doi.org" not in merged_text


def test_pipeline_keeps_structured_abstract_subsections() -> None:
    text = """
## ABSTRACT
## OBJECTIVE
Assess primary effects.
## RESULTS
Main quantitative findings.
## CONCLUSIONS
Short conclusion.
## Introduction
Intro paragraph.
"""
    out = process_markdown(text)
    abstract = next(s for s in out.sections if s.title == "abstract")
    subsection_titles = [sub.title for sub in abstract.subsections]
    assert "objective" in subsection_titles
    assert "results" in subsection_titles
    assert "conclusions" in subsection_titles
    objective = next(sub for sub in abstract.subsections if sub.title == "objective")
    assert any("Assess primary effects." in node.text for node in objective.content)
    introduction = next(s for s in out.sections if s.title == "introduction")
    assert any("Intro paragraph." in node.text for node in introduction.content)


def test_pipeline_skips_acknowledgments_without_heading() -> None:
    text = """
## Conclusion
Main interpretation paragraph.

This review is one of a set of reviews conducted by the Polyunsaturated Fats and Health (PUFAH) Group.
We thank all the authors of primary studies who kindly replied to our queries.
"""
    out = process_markdown(text)
    conclusion = next(s for s in out.sections if s.title == "conclusion")
    merged_text = "\n".join(node.text for node in conclusion.content)
    assert "Main interpretation paragraph." in merged_text
    assert "This review is one of a set of reviews" not in merged_text
    assert "We thank all the authors" not in merged_text


def test_pipeline_skips_fragmented_reference_bullets() -> None:
    text = """
## Discussion
Interpretation paragraph.
- 2016/17): Time trend and income analyses. Public Health England, 2019.
"""
    out = process_markdown(text)
    discussion = next(s for s in out.sections if s.title == "discussion")
    merged_text = "\n".join(node.text for node in discussion.content)
    assert "Interpretation paragraph." in merged_text
    assert "2016/17" not in merged_text


def test_pipeline_merges_hard_wrapped_paragraph_lines() -> None:
    text = """
## Methods
This sentence is split
across two lines.

Second paragraph starts
with another split.
"""
    out = process_markdown(text)
    methods = next(s for s in out.sections if s.title == "methods")
    merged_text = "\n".join(node.text for node in methods.content)
    assert "This sentence is split across two lines." in merged_text
    assert "Second paragraph starts with another split." in merged_text


def test_pipeline_canonicalizes_singular_method_and_result_headings() -> None:
    text = """
## Method
Method body
## Result
Result body
"""
    out = process_markdown(text)
    names = [s.title for s in out.sections]
    assert "methods" in names
    assert "results" in names
    assert "method" not in names
    assert "result" not in names
