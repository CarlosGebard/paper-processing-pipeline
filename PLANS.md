# PLANS.md

## Goal

Add a new `claims` CLI auto-review mode for `<7000` estimated tokens and a `skip-existing` mode that skips any already-generated `*.claims.json` before preview or LLM work.

## Scope

- Add one new `claims` CLI flag for automatic review decisions.
- Add one new `claims` CLI flag for skipping existing outputs.
- Reuse the existing preview and review callback path in the claims flow.
- Keep the current manual claims review mode unchanged.
- Add focused tests for the new behavior.

## Assumptions

- `build_claims_preview()` remains the source of truth for `estimated_input_tokens`.
- A fixed threshold of 7000 estimated input tokens is sufficient for the requested first version.
- Files at or above the threshold should be skipped rather than deferred for manual review in auto mode.
- The skip-existing gate must run before preview generation and before any overwrite path.

## Steps

1. Update `TASKS.md` and this plan so the change is tracked before code edits.
2. Add an early existing-output gate in the claims flow and thread it through the stage/CLI path.
3. Keep the auto-review path for `estimated_input_tokens < 7000`.
4. Expose both options in `paper_pipeline/cli.py` and keep the existing interactive review callback intact.
5. Add focused tests for the token-threshold behavior, skip-existing behavior, and the new CLI help contract.
6. Run the relevant CLI and pytest validations.

## Validation

- Run `python main.py --help`
- Run `python main.py claims --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_scripts_contracts.py -q`

## Risks

- The prompt-size estimate is approximate and may differ from real model tokenization.
- Skipping larger files in auto mode could surprise users if the CLI output is not explicit enough.
- The new skip-existing path must not alter the current overwrite behavior unless the flag is explicitly enabled.
