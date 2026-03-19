MAIN_SECTIONS: dict[str, str] = {
    "title": "title",
    "abstract": "abstract",
    "summary": "abstract",
    "introduction": "introduction",
    "background": "introduction",
    "related work": "introduction",
    "methods": "methods",
    "method": "methods",
    "materials and methods": "methods",
    "materials and method": "methods",
    "materials & methods": "methods",
    "materials & method": "methods",
    "methods and materials": "methods",
    "patients and methods": "methods",
    "patients and method": "methods",
    "methodology": "methods",
    "experimental setup": "methods",
    "results": "results",
    "result": "results",
    "findings": "results",
    "discussion": "discussion",
    "results and discussion": "results_discussion",
    "discussion and conclusions": "discussion",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "concluding remarks": "conclusion",
    "limitations": "limitations",
    "future work": "future work",
    "appendix": "appendix",
    "supplementary material": "supplementary",
    "references": "references",
    "bibliography": "references",
}

SECTION_PREFIX_PATTERNS: dict[str, tuple[str, ...]] = {
    "methods": (
        "methods",
        "method",
        "materials and methods",
        "materials and method",
        "materials & methods",
        "materials & method",
        "methods and materials",
        "patients and method",
        "methodology",
        "experimental",
        "data synthesis",
        "statistical methods",
    ),
    "results": (
        "results",
        "result",
        "experimental results",
        "empirical results",
        "evaluation results",
    ),
    "discussion": (
        "discussion",
        "interpretation",
    ),
    "introduction": (
        "introduction",
        "background",
    ),
    "conclusion": (
        "conclusion",
        "conclusions",
        "concluding",
    ),
    "appendix": (
        "appendix",
    ),
    "references": (
        "references",
        "bibliography",
    ),
}

SUBSECTIONS: set[str] = {
    "objective",
    "design",
    "data sources",
    "eligibility criteria",
    "data synthesis",
    "participants",
    "dataset",
    "study design",
    "statistical analysis",
    "outcomes",
    "ablation",
    "error analysis",
    "inclusion criteria",
    "methods for identification of studies",
    "subgroup analysis",
    "patient and public involvement",
    "description of studies",
    "effects of long chain omega-3",
}

EDITORIAL_NOISE: set[str] = {
    "funding",
    "acknowledgments",
    "acknowledgements",
    "conflicts of interest",
    "author contributions",
    "what is already known on this topic",
    "what this study adds",
}

SUPPLEMENTARY_SECTIONS: set[str] = {
    "supplementary",
    "supplementary material",
}

CUTOFF_SECTIONS: set[str] = {"references"}

PRIORITY_SECTIONS: set[str] = {"methods", "results", "discussion", "results_discussion"}

CANONICAL_PAPER_ORDER: tuple[str, ...] = (
    "title",
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "limitations",
    "future work",
    "appendix",
    "references",
)
