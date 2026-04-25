from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools.paper_selector import PaperCandidate


PAPER_SELECTOR_SYSTEM_PROMPT = """You are a paper-selection agent for a scientific RAG focused on nutrition.

Task:
Decide whether each candidate paper should be kept or dropped for downstream nutrition-focused retrieval.

Keep papers that are clearly relevant or plausibly relevant to topics such as:
- nutrition, diet, dietary patterns, food intake, feeding behavior
- clinical nutrition, public health nutrition, nutritional epidemiology
- obesity, metabolic disease, diabetes, cardiometabolic health when nutrition is central
- dietary interventions, supplements, meal timing, nutrient intake, eating patterns

Prefer (but do not require):
- studies involving humans (clinical, epidemiological, or intervention-based)
- papers likely to contain measurable outcomes related to diet and health

Drop papers that are clearly outside scope, such as:
- non-biomedical topics with no nutrition relevance
- purely molecular, cellular, or mechanistic work with little or no direct nutrition relevance
- papers where title and preview strongly suggest the topic is not about nutrition or diet

Rules:
- Use only the title and abstract preview provided
- The abstract preview may be missing or truncated
- Be moderately recall-oriented but still selective
- If relevance is unclear, return "uncertain"

Output (valid JSON only):
{
  "decision": "keep" | "drop" | "uncertain",
  "reason": "short explanation"
}"""


PAPER_SELECTOR_GAP_SYSTEM_PROMPT = """You are a paper-selection agent for a scientific RAG focused on undercovered nutrition gaps.

Task:
Decide whether each candidate paper should be kept or dropped for downstream retrieval aimed at expanding coverage in missing or weakly covered nutrition areas.

Keep papers that are clearly relevant or plausibly relevant to topics such as:
- micronutrients and deficiencies: iron deficiency anemia, zinc, magnesium, iodine, calcium metabolism, vitamin B12, folate, trace elements
- clinical nutrition and disease nutrition: renal nutrition, chronic kidney disease nutrition, dialysis nutrition, liver nutrition, NAFLD, malnutrition, enteral or parenteral nutrition, cachexia
- life-stage nutrition: pregnancy, maternal nutrition, lactation, infant, pediatric, elderly, aging, sarcopenia
- protein and muscle topics: protein intake, muscle mass, muscle protein synthesis, amino acids, essential amino acids, leucine
- electrolytes and fluids: electrolyte balance, sodium or potassium balance, hydration, fluid balance
- endocrine and hormonal nutrition: endocrine metabolism, insulin signaling, leptin, ghrelin, PCOS nutrition
- nutritional deficiency and biomarkers: malnutrition, undernutrition, nutritional deficiency, nutritional biomarkers, clinical biomarkers nutrition
- food allergies, food intolerances, nutritional epidemiology, and health disparities in nutrition

Prefer papers where nutrition is central to the question, intervention, biomarker, deficiency state, disease management, or life-stage recommendation.

Drop papers that are clearly outside scope, such as:
- broad biomedical work where nutrition is peripheral
- purely mechanistic or molecular studies with no clear nutrition application
- general disease papers with no meaningful focus on diet, nutrients, feeding, biomarkers, or nutrition management

Rules:
- Use only the title and abstract preview provided
- The abstract preview may be missing or truncated
- Be recall-oriented for the listed gap themes, but do not keep generic nutrition papers unless one of those themes is clearly present
- If relevance is unclear, return "uncertain"

Output (valid JSON only):
{
  "decision": "keep" | "drop" | "uncertain",
  "reason": "short explanation"
}"""


def get_paper_selector_system_prompt(selection_profile: str = "broad-nutrition") -> str:
    if selection_profile in {"broad-nutrition", "nutrition-rag"}:
        return PAPER_SELECTOR_SYSTEM_PROMPT
    if selection_profile in {"undercovered-topics", "gap-rag"}:
        return PAPER_SELECTOR_GAP_SYSTEM_PROMPT
    raise ValueError(f"Unknown paper selector profile: {selection_profile}")


def build_paper_selector_user_prompt(candidates: list["PaperCandidate"]) -> str:
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
