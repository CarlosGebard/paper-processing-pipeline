from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

from config_loader import get_config, get_pipeline_paths


PROMPT_TEMPLATE = """You are a scientific information extraction system specialized in health literature.

Your task is to extract high-quality EMPIRICAL health-related claims from the provided sections.

You must act conservatively and stay strictly grounded in the provided text.

<goal>
Extract up to MAX_CLAIMS atomic empirical claims that are explicitly supported by the available sections.
Available sections are listed in AVAILABLE_SECTIONS.
</goal>

<grounding_rules>
- Use only the provided section text.
- Do not use outside knowledge.
- Do not invent missing metadata.
- Claims must be supported by at least one of the available sections.
- You may combine information across available sections only when the connection is explicit in the provided text.
- If support is insufficient, skip the claim.
</grounding_rules>

<what_counts_as_a_valid_claim>
A valid claim must:
- be health-related
- be empirical rather than interpretive
- be supported by the available sections
- express one finding only
- be understandable on its own
- preserve scope and context without overgeneralizing
</what_counts_as_a_valid_claim>

<what_to_extract>
Extract only claims about:
- treatment or intervention effects
- exposure-outcome associations
- risk or risk reduction
- prevention
- diagnosis or prognosis
- symptoms
- biomarkers or physiological outcomes
- disease-related or nutrition-related outcomes
- adverse effects or no-effect findings, when explicitly reported
</what_to_extract>

<what_to_ignore>
Do not extract:
- hypotheses
- mechanistic speculation
- background statements
- author interpretations
- editorial or administrative content
- pure methodology statements with no empirical outcome
- baseline characteristics unless they are themselves reported as a relevant empirical finding
- vague trend language unless a concrete observed result is stated
</what_to_ignore>

<anti_overreach_rules>
- Do not convert association into causation.
- Do not convert subgroup findings into whole-population findings.
- Do not convert non-significant trends into positive effects.
- Do not strengthen wording beyond the evidence.
- Do not merge multiple distinct outcomes into one claim.
- Do not merge multiple distinct populations into one claim unless the text presents them as one inseparable result.
</anti_overreach_rules>

<context_rules>
Use any available section only when it explicitly provides context such as:
- population
- condition
- intervention or exposure
- comparator
- dose
- duration
- study design
- sample size

If a field is not explicitly stated in the provided text, set it to null.
Never guess.
</context_rules>

<numerical_fidelity_rules>
- Preserve reported numbers exactly when available.
- Keep effect sizes, p-values, confidence intervals, and sample sizes faithful to the text.
- Do not recalculate, reinterpret, or embellish numbers.
</numerical_fidelity_rules>

<selection_rules>
- Return no more than MAX_CLAIMS claims.
- Prefer fewer strong claims over many weak claims.
- Prefer claims with clearer outcome, population, and intervention context.
- Avoid duplicates.
- If multiple sentences support the same finding, output one normalized claim and keep the best exact evidence span from RESULTS.
</selection_rules>

<claim_text_rules>
For each output claim:
- write claim_text in English
- make it self-contained
- keep it precise and restrained
- include explicit scope needed to avoid overgeneralization
- use wording that matches the evidential strength
</claim_text_rules>

<confidence_rules>
Assign confidence based only on how directly the claim is supported by the provided text.

Use this scale:
- 0.90 to 1.00 = explicitly stated in the provided sections with clear finding and context
- 0.75 to 0.89 = clearly supported but missing one important contextual element
- 0.60 to 0.74 = supported but less direct or less complete
- below 0.60 = do not output the claim
</confidence_rules>

<output_format>
Return JSON only.
Return an array of objects following this schema exactly:

[
  {
    "claim_text": "string",
    "claim_type": "empirical",
    "support_section": "section title or mixed",
    "population": "string or null",
    "condition": "string or null",
    "intervention_or_exposure": "string or null",
    "comparator": "string or null",
    "outcome": "string or null",
    "direction": "increase | decrease | no_effect | association | difference | null",
    "effect_size": "string or null",
    "dose": "string or null",
    "duration": "string or null",
    "study_design": "string or null",
    "sample_size": "string or null",
    "statistics": {
      "p_value": "string or null",
      "confidence_interval": "string or null",
      "other": "string or null"
    },
    "evidence_span": "exact supporting sentence(s) copied verbatim from the provided section text",
    "confidence": 0.0
  }
]
</output_format>

<final_check>
Before outputting each claim, verify:
1. Is it supported by at least one available section?
2. Is it empirical rather than interpretive?
3. Is it health-related?
4. Is it atomic?
5. Does claim_text avoid stronger wording than the evidence?
6. Did I avoid adding any unstated information?

If any answer is no, exclude the claim.
</final_check>

INPUT VARIABLES:
MAX_CLAIMS = {max_claims}
AVAILABLE_SECTIONS = {available_sections}

[TRACE]
{trace_text}

[SECTIONS]
{sections_text}
"""


SECTION_NOT_FOUND = "_Section not found in source document._"


def load_llm_defaults() -> dict[str, Any]:
    config = get_config()
    paths = get_pipeline_paths(config)
    llm_cfg = config.get("llm_to_claim") or {}
    return {
        "input_dir": paths["claims_input_dir"],
        "output_dir": paths["claims_output_dir"],
        "model": llm_cfg.get("model", "gpt-5-mini"),
        "max_claims": int(llm_cfg.get("max_claims", 10)),
        "temperature": float(llm_cfg.get("temperature", 0.0)),
    }


def parse_args() -> argparse.Namespace:
    defaults = load_llm_defaults()
    parser = argparse.ArgumentParser(
        description="Extract empirical claims from structured post-heuristics files."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=defaults["input_dir"],
        help=(
            "Input JSON/markdown file or directory "
            f"(default desde config.yaml: {defaults['input_dir']})"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=defaults["output_dir"],
        help=(
            "Output JSON file or directory "
            f"(default desde config.yaml: {defaults['output_dir']})"
        ),
    )
    parser.add_argument("--model", type=str, default=defaults["model"], help="Model name")
    parser.add_argument(
        "--max-claims",
        type=int,
        default=defaults["max_claims"],
        help="Maximum number of claims",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=defaults["temperature"],
        help="Sampling temperature",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*/*.final.json",
        help="Glob pattern when --input is a directory",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def parse_markdown_sections(md_text: str) -> dict[str, str]:
    """
    Parse top-level markdown sections like:
    # Trace
    # Abstract
    # Methods
    # Results
    """
    pattern = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(md_text))

    sections: dict[str, str] = {}

    for i, match in enumerate(matches):
        title = match.group(1).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        content = md_text[start:end].strip()
        sections[title] = content

    return sections


def normalize_missing_section(text: str | None) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned == SECTION_NOT_FOUND:
        return ""
    return cleaned


def normalize_section_title(title: str | None) -> str:
    if not title:
        return ""
    lowered = title.strip().lower()
    return re.sub(r"\s+", " ", lowered)


def render_json_section(section: dict[str, Any]) -> str:
    lines: list[str] = []
    text = str(section.get("text", "") or "").strip()
    if text:
        lines.append(text)

    subsections = section.get("subsections", [])
    if isinstance(subsections, list):
        for subsection in subsections:
            if not isinstance(subsection, dict):
                continue
            subsection_title = str(subsection.get("title", "") or "").strip()
            subsection_text = render_json_section(subsection)
            if not subsection_text:
                continue
            if subsection_title:
                lines.append(f"{subsection_title}\n{subsection_text}")
            else:
                lines.append(subsection_text)

    return "\n\n".join(part for part in lines if part).strip()


def render_sections_for_prompt(sections: list[dict[str, Any]]) -> tuple[str, list[str]]:
    rendered_sections: list[str] = []
    available_titles: list[str] = []

    for section in sections:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title", "") or "").strip() or "Untitled Section"
        text = render_json_section(section)
        if not text:
            continue
        available_titles.append(title)
        rendered_sections.append(f"## {title}\n{text}")

    return "\n\n".join(rendered_sections), available_titles


def parse_json_sections(payload: dict[str, Any]) -> dict[str, Any]:
    sections = payload.get("sections", [])
    if not isinstance(sections, list):
        raise ValueError("JSON input does not contain a valid top-level sections list.")
    sections_text, available_titles = render_sections_for_prompt(sections)

    trace_payload = payload.get("trace")
    if isinstance(trace_payload, dict):
        trace_text = json.dumps(trace_payload, ensure_ascii=False, indent=2)
    else:
        trace_text = ""

    return {
        "trace": trace_text,
        "sections_text": sections_text,
        "available_sections": available_titles,
    }


def parse_input_sections(input_path: Path) -> dict[str, Any]:
    suffixes = input_path.suffixes
    if suffixes and suffixes[-1].lower() == ".json":
        return parse_json_sections(read_json(input_path))
    return parse_markdown_sections(read_text(input_path))


def build_prompt(
    trace_text: str,
    sections_text: str,
    max_claims: int,
    available_sections: str,
) -> str:
    return (
        PROMPT_TEMPLATE
        .replace("{trace_text}", trace_text)
        .replace("{sections_text}", sections_text)
        .replace("{max_claims}", str(max_claims))
        .replace("{available_sections}", available_sections)
    )


def extract_text_output(response: Any) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text

    try:
        parts: list[str] = []
        for item in response.output:
            if getattr(item, "type", None) != "message":
                continue
            for content in item.content:
                if getattr(content, "type", None) == "output_text":
                    parts.append(content.text)
        if parts:
            return "\n".join(parts)
    except Exception:
        pass

    raise ValueError("Could not extract text output from API response.")


def validate_claims(data: Any) -> list[dict[str, Any]]:
    """
    Required keys in the schema.
    Values may be null for many contextual fields.
    """
    if not isinstance(data, list):
        raise ValueError("Model output is not a JSON array.")

    required_keys = {
        "claim_text",
        "claim_type",
        "support_section",
        "population",
        "condition",
        "intervention_or_exposure",
        "comparator",
        "outcome",
        "direction",
        "effect_size",
        "dose",
        "duration",
        "study_design",
        "sample_size",
        "statistics",
        "evidence_span",
        "confidence",
    }

    validated: list[dict[str, Any]] = []

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Claim at index {i} is not an object.")

        missing = required_keys - item.keys()
        if missing:
            raise ValueError(f"Claim at index {i} is missing keys: {sorted(missing)}")

        if item["claim_type"] != "empirical":
            raise ValueError(f"Claim at index {i} has invalid claim_type: {item['claim_type']}")

        if not isinstance(item["support_section"], str) or not item["support_section"].strip():
            raise ValueError(f"Claim at index {i} has invalid support_section: {item['support_section']}")

        if not isinstance(item["claim_text"], str) or not item["claim_text"].strip():
            raise ValueError(f"Claim at index {i} has empty claim_text.")

        if not isinstance(item["evidence_span"], str) or not item["evidence_span"].strip():
            raise ValueError(f"Claim at index {i} has empty evidence_span.")

        if not isinstance(item["confidence"], (int, float)):
            raise ValueError(f"Claim at index {i} has invalid confidence.")

        if not isinstance(item["statistics"], dict):
            raise ValueError(f"Claim at index {i} has non-object statistics field.")

        validated.append(item)

    return validated


def derive_output_file(input_path: Path, output: Path) -> Path:
    if output.suffix.lower() == ".json":
        return output

    output_dir = output
    stem = input_path.name
    if stem.endswith(".final.json"):
        stem = stem[: -len(".final.json")]
    elif stem.endswith(".final.md"):
        stem = stem[: -len(".final.md")]
    elif stem.endswith(".json"):
        stem = stem[:-5]
    elif stem.endswith(".md"):
        stem = stem[:-3]
    return output_dir / f"{stem}.claims.json"


def run_claim_extraction_for_file(
    client: OpenAI,
    input_path: Path,
    output_path: Path,
    model: str,
    max_claims: int,
    temperature: float,
) -> int:
    sections = parse_input_sections(input_path)

    trace_text = normalize_missing_section(sections.get("trace"))
    sections_text = normalize_missing_section(sections.get("sections_text"))
    available_sections_list = [str(title) for title in sections.get("available_sections", []) if str(title).strip()]

    prompt = build_prompt(
        trace_text=trace_text,
        sections_text=sections_text,
        max_claims=max_claims,
        available_sections=", ".join(available_sections_list) or "none",
    )

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt}
                ],
            }
        ],
    )

    raw_text = extract_text_output(response)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        print("ERROR: Model output is not valid JSON.", file=sys.stderr)
        print(raw_text, file=sys.stderr)
        raise exc

    claims = validate_claims(parsed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(claims, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(claims)} claims to {output_path}")
    return len(claims)


def collect_input_files(input_path: Path, pattern: str) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(p for p in input_path.glob(pattern) if p.is_file())
    return []


def run_claim_extraction_flow(
    input_path: Path,
    output: Path,
    model: str,
    max_claims: int,
    temperature: float,
    pattern: str = "*/*.final.json",
) -> tuple[int, int, int]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    resolved_input = input_path.expanduser().resolve()
    resolved_output = output.expanduser().resolve()
    files = collect_input_files(resolved_input, pattern)
    if not files:
        print(f"No input files found in {resolved_input} with pattern '{pattern}'.")
        return 0, 0, 0

    client = OpenAI(api_key=api_key)
    processed = 0
    overwritten = 0
    failed = 0

    for file_path in files:
        output_path = derive_output_file(file_path, resolved_output)
        try:
            if output_path.exists():
                overwritten += 1
                print(f"[OVERWRITE] {file_path.name}: regenerando claims en {output_path}")
            run_claim_extraction_for_file(
                client=client,
                input_path=file_path,
                output_path=output_path,
                model=model,
                max_claims=max_claims,
                temperature=temperature,
            )
            processed += 1
        except Exception as exc:
            print(f"[SKIP] {file_path.name}: {exc}", file=sys.stderr)
            failed += 1

    return processed, overwritten, failed


def main() -> int:
    args = parse_args()
    try:
        processed, overwritten, failed = run_claim_extraction_flow(
            input_path=args.input,
            output=args.output,
            model=args.model,
            max_claims=args.max_claims,
            temperature=args.temperature,
            pattern=args.pattern,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("\nResumen llm_to_claim")
    print(f"- Procesados: {processed}")
    print(f"- Overwrite:  {overwritten}")
    print(f"- Fallidos:   {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
