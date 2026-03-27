from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from paper_pipeline.docling_pipeline.section_classifier import DEFAULT_DOTENV_PATH, get_env_value


SYSTEM_PROMPT = """You are a paper-selection agent for a scientific RAG focused on nutrition.

Task:
Decide whether each candidate paper should be kept or dropped for downstream nutrition-focused retrieval.

Keep papers that are clearly relevant or plausibly relevant to topics such as:
- nutrition, diet, dietary patterns, food intake, feeding behavior
- clinical nutrition, public health nutrition, nutritional epidemiology
- obesity, metabolic disease, diabetes, cardiometabolic health when nutrition is central
- dietary interventions, supplements, meal timing, nutrient intake, eating patterns

Drop papers that are clearly outside scope, such as:
- non-biomedical topics with no nutrition relevance
- purely molecular or animal/mechanistic work with no useful nutrition retrieval value
- papers where title and preview strongly suggest the topic is not about nutrition or diet

Rules:
- Use only the title and abstract preview provided.
- The abstract preview may be missing or truncated.
- Be recall-oriented but still selective.
- If relevance is unclear, return "uncertain".
- Return valid JSON only.
"""


OUTPUT_SCHEMA: dict[str, Any] = {
    "name": "paper_selection_decisions",
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
class PaperCandidate:
    id: str
    title: str
    abstract_preview: str


def build_user_prompt(candidates: list[PaperCandidate]) -> str:
    lines: list[str] = []
    for candidate in candidates:
        preview = candidate.abstract_preview.strip() or "No abstract preview available."
        lines.append(
            f"{candidate.id}\n"
            f"TITLE: {candidate.title}\n"
            f"ABSTRACT_PREVIEW: {preview}"
        )

    return (
        "Candidate papers:\n\n"
        + "\n\n".join(lines)
        + "\n\nReturn JSON with this shape:\n"
        + '{"decisions":[{"id":"...","decision":"keep|drop|uncertain","reason":"..."}]}'
    )


def build_responses_payload(model: str, candidates: list[PaperCandidate]) -> dict[str, Any]:
    return {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(candidates)},
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
    candidates: list[PaperCandidate],
) -> list[dict[str, str]]:
    raw_text = extract_output_text(response_json)
    parsed = json.loads(raw_text)
    decisions = parsed.get("decisions", [])
    if not isinstance(decisions, list):
        raise ValueError("La respuesta JSON del modelo no contiene una lista válida en 'decisions'.")

    valid_ids = {candidate.id for candidate in candidates}
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


def classify_papers_with_openai(
    candidates: list[PaperCandidate],
    model: str,
    dotenv_path: str | Path = DEFAULT_DOTENV_PATH,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    api_key = get_env_value("OPENAI_API_KEY", dotenv_path=dotenv_path)
    base_url = get_env_value("OPENAI_BASE_URL", default="https://api.openai.com/v1", dotenv_path=dotenv_path)

    if not api_key:
        raise ValueError("Falta OPENAI_API_KEY en el entorno o en .env.")

    payload = build_responses_payload(model=model, candidates=candidates)
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

    decisions = normalize_decisions(response_json, candidates)
    return decisions, response_json
