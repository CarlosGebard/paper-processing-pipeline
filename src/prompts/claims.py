from __future__ import annotations

CLAIMS_PROMPT_TEMPLATE = """You are a information extraction system specialized in health, nutrition and healthy habits literature.

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


def build_claims_prompt(
    trace_text: str,
    sections_text: str,
    max_claims: int,
    available_sections: str,
) -> str:
    return (
        CLAIMS_PROMPT_TEMPLATE.replace("{trace_text}", trace_text)
        .replace("{sections_text}", sections_text)
        .replace("{max_claims}", str(max_claims))
        .replace("{available_sections}", available_sections)
    )
