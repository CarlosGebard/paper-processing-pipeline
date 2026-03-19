from heuristics_model.normalization import is_likely_false_heading, normalize_heading


def test_normalize_heading_removes_section_numbers() -> None:
    assert normalize_heading("2.3 Methods") == "methods"
    assert normalize_heading("(IV) Results") == "results"


def test_normalize_heading_removes_outer_punctuation() -> None:
    assert normalize_heading("  -- Discussion: ") == "discussion"


def test_false_heading_caption_detection() -> None:
    assert is_likely_false_heading("Figure 1 baseline characteristics", "figure 1 baseline characteristics")


def test_false_heading_sentence_like_detection() -> None:
    assert is_likely_false_heading(
        "This section shows and compares outcomes",
        "this section shows and compares outcomes",
    )
