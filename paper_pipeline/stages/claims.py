from __future__ import annotations

from pathlib import Path

import config_loader as ctx


def run_llm_to_claim_flow(
    input_path: Path | None = None,
    output_path: Path | None = None,
    model: str | None = None,
    max_claims: int | None = None,
    temperature: float | None = None,
    pattern: str = "*/*.final.json",
) -> None:
    ctx.ensure_dirs()
    claims_flow = ctx.resolve_claims_flow()

    source = (input_path or ctx.CLAIMS_INPUT_DIR).expanduser().resolve()
    target = (output_path or ctx.CLAIMS_OUTPUT_DIR).expanduser().resolve()
    chosen_model = model or ctx.LLM_CLAIMS_MODEL
    chosen_temp = temperature if temperature is not None else ctx.LLM_CLAIMS_TEMPERATURE

    processed, skipped = claims_flow(
        source,
        target,
        chosen_model,
        max_claims,
        chosen_temp,
        pattern,
    )

    print("Extraccion de claims completada")
    print(f"- Input:      {ctx.display_path(source)}")
    print(f"- Output:     {ctx.display_path(target)}")
    print(f"- Model:     {chosen_model}")
    print(f"- Max claims: {max_claims if max_claims is not None else 'auto (base 10 + extras)'}")
    print(f"- Processed: {processed}")
    print(f"- Skipped:   {skipped}")
