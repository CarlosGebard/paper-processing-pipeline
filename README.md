# Victus Processing

Paper-processing pipeline for turning scientific papers into metadata, normalized PDFs, Docling artifacts, and claim outputs.

[Español](docs/README.es.md)

## What It Solves

- discovers candidate papers from Semantic Scholar
- stores canonical metadata
- normalizes raw PDFs into pipeline inputs
- runs Docling plus local heuristics
- extracts claims with OpenAI models
- exposes bridge commands for Victus registry, object storage, and events

## Stack

- Python 3.12
- uv
- argparse CLI
- Docling
- OpenAI API
- Semantic Scholar API
- optional Victus bridge: Postgres, Redis, S3-compatible storage

## Run Local

```bash
uv sync
victus-processing --help
victus-processing data-layout create
```

Main flow:

```bash
victus-processing metadata explore --mode broad-nutrition
victus-processing pdfs normalize
victus-processing pipeline run
victus-processing claims extract --skip-existing
```

## Validate

```bash
victus-processing --help
victus-processing metadata --help
victus-processing claims --help
./.venv/bin/python -m pytest tests/test_cli_smoke.py -q
```

Full `pytest tests -q` currently hits stale `analytics/` tests. Track that in [roadmap](docs/roadmap.md).

## Docs

- [Setup](docs/setup.md)
- [Architecture](docs/architecture.md)
- [Contracts](docs/contracts.md)
- [Operations](docs/operations.md)
- [Security](docs/security.md)
- [Tests](docs/tests.md)
- [Roadmap](docs/roadmap.md)
- [Local CLI](ops/scripts/local/README.md)
- [Bridge CLI](ops/scripts/bridge/README.md)
