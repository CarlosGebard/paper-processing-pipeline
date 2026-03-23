from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_dotenv(dotenv_path: str | Path = DEFAULT_DOTENV_PATH) -> dict[str, str]:
    path = Path(dotenv_path).resolve()
    values: dict[str, str] = {}

    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value

    return values


def get_env_value(name: str, default: str = "", dotenv_path: str | Path = DEFAULT_DOTENV_PATH) -> str:
    if name in os.environ:
        env_value = os.environ[name].strip()
        if env_value:
            return env_value

    dotenv_values = load_dotenv(dotenv_path)
    dotenv_value = dotenv_values.get(name, "").strip()
    return dotenv_value or default


SYSTEM_PROMPT = """You classify section titles from scientific papers.

Task:
Decide whether each section title should be kept for downstream evidence extraction.

Keep sections that may contain:
- study methods or design
- participants, eligibility, cohorts, samples
- interventions, exposures, treatments, comparators
- outcomes, endpoints, measurements
- statistical analysis, data synthesis
- results, subgroup analyses, effect estimates, findings

Drop sections that are clearly not useful for evidence extraction:
- abstract or abstract subsections
- introduction or background
- discussion or interpretation-only sections
- conclusions
- references or bibliography
- acknowledgments, funding, conflicts of interest
- ethics, author contributions, supplementary/admin sections

Rules:
- Be recall-oriented: if a section might contain useful evidence, keep it.
- Drop only if the section is clearly irrelevant.
- If uncertain, return "uncertain".
- Infer meaning from the title, not only exact string matches.
- The paper title is provided for context only.
- Return valid JSON only.
"""


OUTPUT_SCHEMA: dict[str, Any] = {
    "name": "section_decisions",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "decision": {
                            "type": "string",
                            "enum": ["keep", "drop", "uncertain"],
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "decision", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["decisions"],
        "additionalProperties": False,
    },
}


@dataclass
class SectionCandidate:
    id: str
    title: str
    level: int


def build_user_prompt(paper_title: str, sections: list[SectionCandidate]) -> str:
    lines = [f"{section.id} | level={section.level} | title={section.title}" for section in sections]
    numbered_list = "\n".join(lines)

    return (
        f"Paper title:\n{paper_title}\n\n"
        f"Section titles:\n{numbered_list}\n\n"
        "Return JSON with this shape:\n"
        '{"decisions":[{"id":"...","decision":"keep|drop|uncertain","reason":"..."}]}'
    )


def build_responses_payload(model: str, paper_title: str, sections: list[SectionCandidate]) -> dict[str, Any]:
    return {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(paper_title, sections)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": OUTPUT_SCHEMA["name"],
                "strict": OUTPUT_SCHEMA["strict"],
                "schema": OUTPUT_SCHEMA["schema"],
            }
        },
    }


def extract_output_text(response_json: dict[str, Any]) -> str:
    output = response_json.get("output", [])
    if not isinstance(output, list):
        raise ValueError("La respuesta de OpenAI no contiene una lista válida en 'output'.")

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                return text

    raise ValueError("No se encontró texto JSON en la respuesta de OpenAI.")


def normalize_decisions(
    response_json: dict[str, Any],
    sections: list[SectionCandidate],
) -> list[dict[str, str]]:
    raw_text = extract_output_text(response_json)
    parsed = json.loads(raw_text)
    decisions = parsed.get("decisions", [])
    if not isinstance(decisions, list):
        raise ValueError("La respuesta JSON del modelo no contiene una lista válida en 'decisions'.")

    valid_ids = {section.id for section in sections}
    normalized: list[dict[str, str]] = []

    for item in decisions:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "")).strip()
        decision = str(item.get("decision", "")).strip()
        reason = str(item.get("reason", "")).strip()

        if item_id not in valid_ids:
            continue
        if decision not in {"keep", "drop", "uncertain"}:
            continue

        normalized.append(
            {
                "id": item_id,
                "decision": decision,
                "reason": reason,
            }
        )

    missing_ids = valid_ids - {item["id"] for item in normalized}
    for missing_id in sorted(missing_ids):
        normalized.append(
            {
                "id": missing_id,
                "decision": "uncertain",
                "reason": "missing_from_model_output",
            }
        )

    return sorted(normalized, key=lambda item: item["id"])


def classify_sections_with_openai(
    paper_title: str,
    sections: list[SectionCandidate],
    dotenv_path: str | Path = DEFAULT_DOTENV_PATH,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    api_key = get_env_value("OPENAI_API_KEY", dotenv_path=dotenv_path)
    model = get_env_value("OPENAI_MODEL", default="gpt-5-mini", dotenv_path=dotenv_path)
    base_url = get_env_value("OPENAI_BASE_URL", default="https://api.openai.com/v1", dotenv_path=dotenv_path)

    if not api_key:
        raise ValueError("Falta OPENAI_API_KEY en el entorno o en .env.")

    payload = build_responses_payload(model=model, paper_title=paper_title, sections=sections)
    body = json.dumps(payload).encode("utf-8")

    req = request.Request(
        url=f"{base_url.rstrip('/')}/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req) as resp:
            response_json = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Error HTTP al llamar a OpenAI: {exc.code} {detail}") from exc

    decisions = normalize_decisions(response_json, sections)
    return decisions, response_json
