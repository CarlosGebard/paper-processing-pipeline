from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from .normalization import normalize_heading

_CORE_SECTIONS: tuple[str, ...] = ("methods", "results", "discussion")
_RECOMMENDED_SECTIONS: tuple[str, ...] = ("abstract", "introduction", "conclusion")
_EDITORIAL_LEAK_RE = re.compile(
    r"(?:^|\b)(?:we thank all the authors|members of the pufah group are|this review is one of a set of reviews conducted by|contributors:|funding:|competing interests:|transparency declaration:|data sharing:)",
    re.IGNORECASE,
)
_REFERENCE_LEAK_RE = re.compile(
    r"^\s*[-*]\s*(?:\d+\s+[A-Za-z]|\d{3,4}(?:/\d{1,4})+\)\s*:)",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _split_sections(markdown_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        match = _HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 1:
            current_section = normalize_heading(match.group(2))
            sections.setdefault(current_section, [])
            continue
        if current_section is not None:
            sections[current_section].append(line)
    return sections


def _count_dangling_short_lines(markdown_text: str) -> int:
    lines = markdown_text.splitlines()
    count = 0

    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("#", "##", "###", "-", "*", "|", "<!--")):
            continue
        if line.endswith((".", ";", ":", "?", "!", ")")):
            continue

        words = re.findall(r"\b\w+\b", line)
        if len(words) == 0 or len(words) > 4:
            continue

        previous_line = lines[idx - 1].strip() if idx > 0 else ""
        next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        if previous_line and next_line:
            count += 1

    return count


def diagnose_markdown(markdown_text: str) -> dict[str, Any]:
    sections = _split_sections(markdown_text)
    section_names = set(sections.keys())

    missing_core = [name for name in _CORE_SECTIONS if name not in section_names]
    missing_recommended = [name for name in _RECOMMENDED_SECTIONS if name not in section_names]

    abstract_lines = sections.get("abstract", [])
    abstract_text = "\n".join(line for line in abstract_lines if line.strip() and not line.strip().startswith("## "))
    abstract_subsections = sum(1 for line in abstract_lines if line.strip().startswith("## "))

    editorial_hits: list[str] = []
    reference_hits: list[str] = []
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _EDITORIAL_LEAK_RE.search(stripped):
            editorial_hits.append(stripped)
        if _REFERENCE_LEAK_RE.match(stripped):
            reference_hits.append(stripped)

    dangling_short_lines = _count_dangling_short_lines(markdown_text)

    score = 100
    score -= 20 * len(missing_core)
    score -= 15 if not abstract_text.strip() else 0
    score -= 5 * len(missing_recommended)
    score -= 10 if editorial_hits else 0
    score -= 10 if reference_hits else 0
    score -= min(15, (dangling_short_lines // 5) * 5)
    score = max(0, min(100, score))

    failures: list[str] = []
    warnings: list[str] = []
    if missing_core:
        failures.append(f"Missing core sections: {', '.join(missing_core)}")
    if not abstract_text.strip():
        failures.append("Abstract has no body text")
    if editorial_hits:
        failures.append("Editorial leakage detected in output")
    if reference_hits:
        failures.append("Reference leakage detected before cutoff")
    if missing_recommended:
        warnings.append(f"Missing recommended sections: {', '.join(missing_recommended)}")
    if abstract_subsections == 0 and "abstract" in section_names:
        warnings.append("Abstract has no structured subsections")
    if dangling_short_lines >= 8:
        warnings.append(f"Potential hard-wrap residue: {dangling_short_lines} short dangling lines")

    status = "pass" if not failures else "fail"
    return {
        "status": status,
        "score": score,
        "metrics": {
            "section_count": len(section_names),
            "missing_core_sections": missing_core,
            "missing_recommended_sections": missing_recommended,
            "abstract_chars": len(abstract_text.strip()),
            "abstract_subsections": abstract_subsections,
            "editorial_leak_count": len(editorial_hits),
            "reference_leak_count": len(reference_hits),
            "dangling_short_lines": dangling_short_lines,
        },
        "failures": failures,
        "warnings": warnings,
        "samples": {
            "editorial_leaks": editorial_hits[:5],
            "reference_leaks": reference_hits[:5],
        },
    }


def _collect_markdown_files(path: Path, pattern: str) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob(pattern) if p.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description="Quality diagnostics for processed markdown output")
    parser.add_argument("path", type=Path, help="Markdown file or directory")
    parser.add_argument("--glob", default="*.md", help="Glob when path is a directory")
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Diagnostics output format",
    )
    args = parser.parse_args()

    files = _collect_markdown_files(args.path, args.glob)
    if not files:
        raise SystemExit("No markdown files found for diagnostics")

    results: list[dict[str, Any]] = []
    for file_path in files:
        report = diagnose_markdown(file_path.read_text(encoding="utf-8"))
        report["file"] = str(file_path)
        results.append(report)

    failing = [item for item in results if item["status"] == "fail"]
    summary = {
        "total_files": len(results),
        "pass_files": len(results) - len(failing),
        "fail_files": len(failing),
    }

    payload: dict[str, Any] = {
        "summary": summary,
        "results": results,
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Files: {summary['total_files']} | pass: {summary['pass_files']} | fail: {summary['fail_files']}")
        for result in results:
            print(f"- {result['file']}: {result['status']} (score={result['score']})")
            for failure in result["failures"]:
                print(f"  FAIL: {failure}")
            for warning in result["warnings"]:
                print(f"  WARN: {warning}")

    raise SystemExit(1 if failing else 0)


if __name__ == "__main__":
    main()
