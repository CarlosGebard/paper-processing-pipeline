from heuristics_model.classifier import classify_heading


def test_classifies_main_section() -> None:
    result = classify_heading("methods", level=2, raw_heading="Methods")
    assert result.role == "section"
    assert result.canonical_label == "methods"


def test_classifies_main_section_by_prefix() -> None:
    result = classify_heading("methods for identification of studies", level=2, raw_heading="Methods for identification of studies")
    assert result.role == "section"
    assert result.canonical_label == "methods"


def test_classifies_singular_method_heading() -> None:
    result = classify_heading("method", level=2, raw_heading="Method")
    assert result.role == "section"
    assert result.canonical_label == "methods"


def test_classifies_singular_result_heading() -> None:
    result = classify_heading("result", level=2, raw_heading="Result")
    assert result.role == "section"
    assert result.canonical_label == "results"


def test_classifies_subsection_by_level_fallback() -> None:
    result = classify_heading("sample collection details", level=2, raw_heading="Sample collection details")
    assert result.role == "subsection"


def test_false_heading_is_reclassified_to_text() -> None:
    result = classify_heading(
        "this section shows and compares outcomes",
        level=2,
        raw_heading="This section shows and compares outcomes",
    )
    assert result.role == "text"
    assert result.canonical_label is None
