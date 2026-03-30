from __future__ import annotations

from pathlib import Path
from typing import Any

from src import config as ctx


def run_llm_to_claim_flow(
    input_path: Path | None = None,
    output_path: Path | None = None,
    model: str | None = None,
    max_claims: int | None = None,
    temperature: float | None = None,
    pattern: str = "*/*.final.json",
    review_callback: Any = None,
    auto_approve_max_tokens: int | None = None,
    skip_existing: bool = False,
) -> None:
    ctx.ensure_dirs()
    claims_flow = ctx.resolve_claims_flow()

    source = (input_path or ctx.CLAIMS_INPUT_DIR).expanduser().resolve()
    target = (output_path or ctx.CLAIMS_OUTPUT_DIR).expanduser().resolve()
    chosen_model = model or ctx.LLM_CLAIMS_MODEL
    chosen_temp = temperature if temperature is not None else ctx.LLM_CLAIMS_TEMPERATURE

    processed, overwritten, failed = claims_flow(
        source,
        target,
        chosen_model,
        max_claims,
        chosen_temp,
        pattern,
        review_callback,
        auto_approve_max_tokens,
        skip_existing,
    )

    print("Extraccion de claims completada")
    print(f"- Input:      {ctx.display_path(source)}")
    print(f"- Output:     {ctx.display_path(target)}")
    print(f"- Model:     {chosen_model}")
    print(f"- Max claims: {max_claims if max_claims is not None else 'auto (base 10 + extras)'}")
    print(
        f"- Auto approve: {f'< {auto_approve_max_tokens} tokens' if auto_approve_max_tokens is not None else 'off'}"
    )
    print(f"- Skip existing: {'on' if skip_existing else 'off'}")
    print(f"- Processed: {processed}")
    print(f"- Overwrite: {overwritten}")
    print(f"- Failed:    {failed}")
