from heuristics_model.diagnostics import diagnose_markdown


def test_diagnostics_pass_on_clean_structure() -> None:
    text = """
# Abstract
## Objective
Objective text.
## Results
Result summary text.
# Introduction
Intro text.
# Methods
Methods text.
# Results
Results text.
# Discussion
Discussion text.
# Conclusion
Conclusion text.
"""
    report = diagnose_markdown(text)
    assert report["status"] == "pass"
    assert report["metrics"]["missing_core_sections"] == []
    assert report["metrics"]["abstract_chars"] > 0
    assert report["metrics"]["editorial_leak_count"] == 0
    assert report["metrics"]["reference_leak_count"] == 0


def test_diagnostics_fail_on_editorial_and_reference_leakage() -> None:
    text = """
# Abstract
## Objective
Objective text.
# Methods
Methods text.
# Results
Results text.
# Discussion
This review is one of a set of reviews conducted by the Polyunsaturated Fats and Health Group.
- 2016/17): Time trend and income analyses. Public Health England, 2019.
"""
    report = diagnose_markdown(text)
    assert report["status"] == "fail"
    assert report["metrics"]["editorial_leak_count"] > 0
    assert report["metrics"]["reference_leak_count"] > 0
    assert report["failures"]


def test_diagnostics_fail_when_abstract_body_missing() -> None:
    text = """
# Abstract
# Introduction
Intro text.
# Methods
Methods text.
# Results
Results text.
# Discussion
Discussion text.
"""
    report = diagnose_markdown(text)
    assert report["status"] == "fail"
    assert "Abstract has no body text" in report["failures"]
