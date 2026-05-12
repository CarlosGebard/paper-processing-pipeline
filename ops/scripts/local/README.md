# Local CLI

Local pipeline CLI for `victus-processing`.

Preferred command after `uv sync`:

```bash
victus-processing --help
```

Path fallback:

```bash
python ops/scripts/local/cli.py --help
```

## Owns

- local pipeline command groups
- argparse parser and flags
- handlers that call `src/stages` or `ops/scripts/*.py`

## Does Not Own

- runtime config: `src/config.py`
- pipeline stage logic: `src/stages`
- document tools: `src/tools`
- bridge internals: `ops/scripts/bridge`

## Commands

```bash
victus-processing metadata --help
victus-processing bib --help
victus-processing pdfs --help
victus-processing pipeline --help
victus-processing claims --help
victus-processing bridge --help
victus-processing data-layout --help
```

## Validation

```bash
victus-processing --help
victus-processing metadata --help
victus-processing claims --help
victus-processing bridge --help
./.venv/bin/python -m pytest tests/test_cli_smoke.py -q
```
