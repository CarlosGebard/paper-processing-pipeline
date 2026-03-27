from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from config_loader import get_config, get_pipeline_paths
from paper_pipeline.artifacts import record_claims_run


PROMPT_TEMPLATE = """You are a information extraction system specialized in health, nutrition and healthy habits literature.

Task: extract up to MAX_CLAIMS atomic empirical health-related claims explicitly supported by the provided sections.

<rules>
- Use only the provided section text.
- Do not use outside knowledge.
- Do not invent or guess missing metadata.
- Claims must be supported by at least one of the available sections.
- Combine information across sections only when the link is explicit in the text.
- If support is insufficient, skip the claim.
</rules>

<include>
Extract only empirical claims about:
- dietary patterns, foods, nutrients, meal timing, or nutrition-related exposures
- lifestyle or healthy-habit exposures when explicitly health-related
- nutrition-, diet-, supplement-, or lifestyle-related interventions when the text reports an explicit health-related empirical finding
- exposure-outcome associations
- risk, risk reduction, or prevention
- biomarkers, physiological outcomes, disease-related outcomes
- adverse effects or explicit no-effect findings
</include>

<claim_requirements>
Each claim must:
- be health-related
- be empirical, not interpretive
- express one finding only
- be understandable on its own without requiring surrounding narrative context
- preserve the scope of the evidence without overgeneralizing
</claim_requirements>

<exclude>
Do not extract:
- hypotheses
- mechanistic speculation
- background statements
- author interpretations
- editorial or administrative content
- methodology without an empirical finding
- baseline characteristics unless reported as a relevant finding 
- vague trend without a concrete observed result 
</exclude>

<anti_overreach>
- Do not convert association into causation.
- Do not convert subgroup findings into whole-population findings.
- Do not convert non-significant trends into positive effects.
- Do not strengthen wording beyond the evidence.
- Do not merge distinct outcomes into one claim.
- Do not merge distinct populations into one claim unless the text presents them as one inseparable result.
</anti_overreach>

<context>
Use available sections to capture context only when explicit:
population, condition, intervention_or_exposure, comparator, dose, duration, study_design, sample_size.
If a field is not explicit, set it to null.
</context>

<numerical_fidelity_rules>
- Preserve reported numbers exactly when available.
- Keep effect sizes, p-values, confidence intervals, and sample sizes faithful to the text.
- Do not recalculate, reinterpret, or embellish numbers.
</numerical_fidelity_rules>

<selection>
- Return no more than MAX_CLAIMS claims.
- Prefer fewer strong claims over many weak claims.
- Prefer claims with clearer outcome, population, and intervention context.
- Avoid duplicates.
- If multiple sentences support the same finding, output one normalized claim and keep the best exact evidence span.
</selection>

<claim_text>
For each claim:
- write claim_text in English
- make it self-contained
- keep it precise and restrained
- include scope needed to avoid overgeneralization
- use wording that matches the evidential strength
</claim_text>

<keywords>
For each claim, extract 3 to 8 retrieval-oriented keywords grounded only in the provided text.
Keywords should prioritize:
- intervention_or_exposure
- outcome
- population or condition
- explicit abbreviations or synonyms only if stated in the text
Use short noun phrases, not sentences.
Do not add background concepts not explicitly supported by the text.
</keywords>

<confidence>
Assign confidence based only on how directly the claim is supported by the provided text.

Use this scale:
- 0.90 to 1.00 = explicit finding with clear context
- 0.75 to 0.89 = clear support but one important context element missing 
- 0.60 to 0.74 = supported but less direct or less complete 
- below 0.60 = do not output
</confidence>

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
    "keywords": ["string"],
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
3. Is it nutrition / health-related?
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


BASE_CLAIMS = 10
MAX_EXTRA_CLAIMS = 10
MIN_CITATIONS = 100
MAX_CITATIONS = 2000
MIN_WORD_COUNT = 1500
MAX_WORD_COUNT = 12000
CITATION_WEIGHT = 0.35
TEXT_WEIGHT = 0.65
AUTO_APPROVE_MAX_TOKENS = 7000


def load_llm_defaults() -> dict[str, Any]:
    config = get_config()
    paths = get_pipeline_paths(config)
    llm_cfg = config.get("llm_to_claim") or {}
    return {
        "input_dir": paths["claims_input_dir"],
        "output_dir": paths["claims_output_dir"],
        "model": llm_cfg.get("model", "gpt-5-mini"),
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
            "Input final JSON file or directory "
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
        default=None,
        help=f"Fixed max claims override (default auto: base {BASE_CLAIMS} + extras)",
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
    parser.add_argument(
        "--auto-approve-under-7000-tokens",
        action="store_true",
        help=(
            "Procesa automaticamente solo archivos con estimated_input_tokens "
            f"menor a {AUTO_APPROVE_MAX_TOKENS}"
        ),
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Salta archivos cuyo *.claims.json de salida ya existe",
    )
    return parser.parse_args()

def read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def normalize_missing_section(text: str | None) -> str:
    if not text:
        return ""
    return text.strip()


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def count_words(text: str) -> int:
    return len(text.split()) if text.strip() else 0


def normalize_linear(value: int, minimum: int, maximum: int) -> float:
    if maximum <= minimum:
        return 0.0
    return clamp((value - minimum) / (maximum - minimum))


def compute_dynamic_claim_limit(
    citation_count: int | None,
    word_count: int,
    base_claims: int = BASE_CLAIMS,
) -> dict[str, Any]:
    normalized_citations = normalize_linear(citation_count or 0, MIN_CITATIONS, MAX_CITATIONS)
    normalized_text = normalize_linear(word_count, MIN_WORD_COUNT, MAX_WORD_COUNT)
    combined_score = (CITATION_WEIGHT * normalized_citations) + (TEXT_WEIGHT * normalized_text)
    extra_claims = int(round(combined_score * MAX_EXTRA_CLAIMS))
    return {
        "base_claims": base_claims,
        "extra_claims": extra_claims,
        "final_claims": base_claims + extra_claims,
        "citation_count": citation_count,
        "word_count": word_count,
        "normalized_citations": round(normalized_citations, 4),
        "normalized_text": round(normalized_text, 4),
        "combined_score": round(combined_score, 4),
        "mode": "dynamic",
    }


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

    paper = payload.get("paper") if isinstance(payload.get("paper"), dict) else {}
    paper_data = dict(paper) if isinstance(paper, dict) else {}
    if not str(paper_data.get("title") or "").strip():
        top_level_title = str(payload.get("paper_title") or payload.get("title") or "").strip()
        if top_level_title:
            paper_data["title"] = top_level_title

    return {
        "trace": trace_text,
        "sections_text": sections_text,
        "available_sections": available_titles,
        "paper": paper_data,
    }


def parse_input_sections(input_path: Path) -> dict[str, Any]:
    if input_path.suffix.lower() != ".json":
        raise ValueError(f"Claims extraction solo soporta archivos JSON final, no: {input_path.name}")
    return parse_json_sections(read_json(input_path))


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


def estimate_text_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, round(len(stripped) / 4))


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
    elif stem.endswith(".json"):
        stem = stem[:-5]
    return output_dir / f"{stem}.claims.json"


def build_claims_preview(
    input_path: Path,
    max_claims: int | None,
) -> dict[str, Any]:
    sections = parse_input_sections(input_path)
    trace_text = normalize_missing_section(sections.get("trace"))
    sections_text = normalize_missing_section(sections.get("sections_text"))
    available_sections_list = [str(title) for title in sections.get("available_sections", []) if str(title).strip()]
    paper = sections.get("paper") if isinstance(sections.get("paper"), dict) else {}
    citation_count_raw = paper.get("citation_count")
    citation_count = int(citation_count_raw) if isinstance(citation_count_raw, (int, float)) else None
    word_count = count_words(sections_text)
    claims_limit = (
        {
            "base_claims": BASE_CLAIMS,
            "extra_claims": 0,
            "final_claims": max_claims,
            "citation_count": citation_count,
            "word_count": word_count,
            "normalized_citations": None,
            "normalized_text": None,
            "combined_score": None,
            "mode": "fixed_override",
        }
        if max_claims is not None
        else compute_dynamic_claim_limit(citation_count, word_count)
    )
    prompt = build_prompt(
        trace_text=trace_text,
        sections_text=sections_text,
        max_claims=int(claims_limit["final_claims"]),
        available_sections=", ".join(available_sections_list) or "none",
    )
    title = str(paper.get("title") or input_path.stem).strip() or input_path.stem
    return {
        "title": title,
        "section_count": len(available_sections_list),
        "available_sections": available_sections_list,
        "estimated_input_tokens": estimate_text_tokens(prompt),
        "claims_limit": claims_limit,
        "paper": paper,
        "word_count": word_count,
    }


def run_claim_extraction_for_file(
    client: OpenAI,
    input_path: Path,
    output_path: Path,
    model: str,
    max_claims: int | None,
    temperature: float,
) -> int:
    sections = parse_input_sections(input_path)
    preview = build_claims_preview(input_path, max_claims)
    trace_text = normalize_missing_section(sections.get("trace"))
    sections_text = normalize_missing_section(sections.get("sections_text"))
    available_sections_list = [str(title) for title in sections.get("available_sections", []) if str(title).strip()]
    paper = sections.get("paper") if isinstance(sections.get("paper"), dict) else {}
    claims_limit = preview["claims_limit"]

    prompt = build_prompt(
        trace_text=trace_text,
        sections_text=sections_text,
        max_claims=int(claims_limit["final_claims"]),
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
    doi = str(paper.get("doi") or "").strip()
    document_id = str(paper.get("paper_id") or "").strip()
    base_name = input_path.name[: -len(".final.json")] if input_path.name.endswith(".final.json") else input_path.stem
    if doi:
        record_claims_run(
            document_id=document_id,
            doi=doi,
            base_name=base_name,
            claims_run={
                **claims_limit,
                "extracted_claims": len(claims),
                "output_path": str(output_path),
            },
        )
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
    max_claims: int | None,
    temperature: float,
    pattern: str = "*/*.final.json",
    review_callback: Callable[[Path, dict[str, Any], Path], bool] | None = None,
    auto_approve_max_tokens: int | None = None,
    skip_existing: bool = False,
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
    deferred_files: list[Path] = []

    for file_path in files:
        output_path = derive_output_file(file_path, resolved_output)
        try:
            if skip_existing and output_path.exists():
                print(f"[SKIP EXISTING] {file_path.name}: ya existe {output_path}")
                continue
            preview = build_claims_preview(file_path, max_claims)
            estimated_tokens = int(preview.get("estimated_input_tokens") or 0)
            if auto_approve_max_tokens is not None:
                if estimated_tokens < auto_approve_max_tokens:
                    print(
                        f"[AUTO-APPROVE] {file_path.name}: "
                        f"{estimated_tokens} tokens < {auto_approve_max_tokens}"
                    )
                else:
                    print(
                        f"[SKIP AUTO] {file_path.name}: "
                        f"{estimated_tokens} tokens >= {auto_approve_max_tokens}"
                    )
                    continue
            if review_callback is not None:
                preview["review_phase"] = "initial"
                preview["output_exists"] = output_path.exists()
                decision = review_callback(file_path, preview, output_path)
                if not decision:
                    deferred_files.append(file_path)
                    print(f"[STANDBY] {file_path.name}: movido al final de la cola")
                    continue
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

    for file_path in deferred_files:
        output_path = derive_output_file(file_path, resolved_output)
        try:
            if review_callback is not None:
                preview = build_claims_preview(file_path, max_claims)
                preview["review_phase"] = "final"
                preview["output_exists"] = output_path.exists()
                if not review_callback(file_path, preview, output_path):
                    print(f"[SKIP] {file_path.name}: rechazado por usuario en revision final")
                    continue
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
            auto_approve_max_tokens=(
                AUTO_APPROVE_MAX_TOKENS if args.auto_approve_under_7000_tokens else None
            ),
            skip_existing=args.skip_existing,
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
