from __future__ import annotations


CLAIMS_PROMPT_TEMPLATE = """You are an information extraction system specialized in health, nutrition, and healthy-habits literature.

Task: extract up to MAX_CLAIMS atomic empirical health-related claims explicitly supported by the provided content.

Goal: extract the strongest supported empirical claims with faithful structure, precise wording, and exact evidence grounding. Do not summarize.

<RULES>
- Use only the provided content.
- Narrative results text, tables, and figure-related text are all valid evidence sources.
- Do not use outside knowledge.
- Do not infer or guess missing metadata.
- If a field is not explicit, set it to null.
- If support is weak or ambiguous, skip the claim.
- Prefer fewer strong claims over many weak or redundant claims.
</RULES>

<INCLUDE>
Extract only empirical health-related findings about:
- diet, foods, nutrients, supplements, meal timing, lifestyle, or healthy-habit exposures/interventions
- clinical, physiological, biomarker, disease, risk, prevalence, incidence, or prognostic outcomes
- adverse effects, tolerability, harms, or explicit no-effect findings
- adherence/compliance biomarkers only when they are measured findings
</INCLUDE>

<EXCLUDE>
Do not extract:
- hypotheses, speculation, mechanisms, background facts, editorial/admin text
- methods without results
- pure baseline descriptions unless presented as a relevant finding
- vague trends without a concrete observed result
- broad conclusions when a more specific supported finding is available
</EXCLUDE>

<CLAIM_RULES>
Each claim must be:
- empirical
- health-related
- atomic
- self-contained
- scoped to the reported population/subgroup/timepoint/comparison
Do not:
- convert association into causation
- convert within-group change into between-group superiority
- convert subgroup findings into whole-population findings
- convert non-significant trends into positive effects
- merge distinct outcomes or distinct populations into one claim
- treat adherence biomarkers as primary outcomes unless explicitly defined that way
</CLAIM_RULES>

<EVIDENCE_SELECTION>
Use the strongest explicit support available for each claim.
Prefer:
1. explicit comparator-based findings
2. primary/clinical outcomes
3. secondary outcomes
4. adherence biomarkers
5. safety/no-effect findings

If the same finding appears in both text and table:
- use the source with the most precise support
- prefer tables for clearer quantitative detail
- prefer narrative text for context such as subgroup scope, timing, adjustment, or significance
Do not assume tables are always better.
Use Discussion only when it directly restates an empirical finding supported in the provided content.
</EVIDENCE_SELECTION>

<STRUCTURE>
Capture when explicit:
population, condition, subgroup, intervention_or_exposure, comparator, arm, comparator_arm, outcome, dose, duration, timepoint, study_design, sample_size.

Set comparison_type as:
- "between_group" = explicit comparison across arms/groups/categories
- "within_group" = explicit pre/post or baseline/follow-up change within one group
- "association" = observational association without intervention comparison
- null = unclear or not applicable

If baseline/follow-up values are explicitly reported, extract them.
If only change is reported, extract only the change.
Do not recalculate missing values.

Classify each claim into exactly one:
- "primary_outcome"
- "secondary_outcome"
- "adherence_biomarker"
- "safety"
- "risk_association"
- "other_empirical"
</STRUCTURE>

<NUMERICAL_FIDELITY>
- Preserve numbers exactly as reported.
- Preserve signs, units, p-values, confidence intervals, and uncertainty terms exactly.
- Do not recalculate, standardize, or embellish.
- Do not convert vague wording like "changed little" into numeric no-effect unless a number is given.
</NUMERICAL_FIDELITY>

<SELECTION>
- Return no more than MAX_CLAIMS claims.
- Prefer stronger and more retrieval-useful claims.
- Prefer explicit numbers when they support the same finding more precisely.
- Avoid duplicates and near-duplicates.
- Separate distinct findings when meaningful and non-redundant.
- Do not overfill with minor adherence claims if stronger primary/comparator findings exist.
</SELECTION>

<CLAIM_TEXT>
For each claim:
- write claim_text in English
- keep it precise, restrained, and self-contained
- preserve whether it is a between-group finding, within-group change, or association
- mention a comparator only if explicitly reported
</CLAIM_TEXT>

<KEYWORDS>
Extract 3 to 8 short retrieval-oriented keywords grounded only in the content.
Prioritize:
- intervention/exposure
- comparator or arm when relevant
- outcome
- population/subgroup/condition
- explicit abbreviations only if stated
No sentences. No unstated concepts.
</KEYWORDS>

<CONFIDENCE>
Assign confidence only from directness/completeness of support:
- 0.90 to 1.00 = explicit finding with clear support
- 0.75 to 0.89 = clear finding but one key context element missing
- 0.60 to 0.74 = supported but weaker or less complete
- below 0.60 = do not output
</CONFIDENCE>

<OUTPUT>
Return JSON only as an array with this exact schema:

[
  {
    "claim_text": "string",
    "claim_type": "empirical",
    "claim_family": "primary_outcome | secondary_outcome | adherence_biomarker | safety | risk_association | other_empirical",
    "support_section": "section title or mixed",
    "population": "string or null",
    "condition": "string or null",
    "subgroup": "string or null",
    "intervention_or_exposure": "string or null",
    "comparator": "string or null",
    "arm": "string or null",
    "comparator_arm": "string or null",
    "comparison_type": "between_group | within_group | association | null",
    "outcome": "string or null",
    "direction": "increase | decrease | no_effect | association | difference | null",
    "units": "string or null",
    "baseline_value": "string or null",
    "followup_value": "string or null",
    "within_group_change": "string or null",
    "between_group_difference": "string or null",
    "effect_size": "string or null",
    "dose": "string or null",
    "duration": "string or null",
    "timepoint": "string or null",
    "study_design": "string or null",
    "sample_size": "string or null",
    "keywords": ["string"],
    "statistics": {
      "p_value": "string or null",
      "confidence_interval": "string or null",
      "other": "string or null"
    },
    "evidence_span": "exact supporting sentence(s) or exact table/figure-related text copied verbatim from the provided content",
    "confidence": 0.0
  }
]
</OUTPUT>

<CHECK>
Before outputting each claim, verify:
- explicitly supported
- empirical
- health-related
- atomic
- not overstated
- no unstated metadata added
- correct claim_family
- correct comparison_type
- exact numerical fidelity preserved
If any check fails, exclude the claim.
</CHECK>

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
