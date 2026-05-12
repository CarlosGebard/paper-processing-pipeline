# Roadmap

## Next

- Remove or migrate stale `analytics/` tests.
- Decide whether analytics stays external or returns as a separate package.
- Audit `docs/tests.md` and split/keep/delete tests by current repo boundary.
- Add CI for CLI smoke tests.
- Add linting and formatting config.

## Technical Debt

- `AGENTS.md` still references older names like `config_loader.py` and `paper_pipeline/`.
- CLI parser and handlers still live in one `commands.py` file.
- Bridge uses manual S3 signing.
- No typed contract tests exist for bridge event payloads.

## Open Decisions

- Whether bridge should remain a nested package or become its own repo.
- Whether local CLI should be split into domain modules.
- Whether `data/README.md` needs replacement as generated data documentation later.
