# Setup

## Requirements

- Python 3.12
- uv
- network access for API-driven commands
- optional bridge services: Postgres, Redis, S3-compatible storage

## Install

```bash
uv sync
```

Bridge package, only when using `victus-ingest` directly:

```bash
cd ops/scripts/bridge
uv sync
```

## Environment

Local pipeline:

```text
SEMANTIC_SCHOLAR_API_KEY=
OPENAI_API_KEY=
```

Bridge:

```text
VICTUS_PG_DSN=
VICTUS_REDIS_URL=redis://redis:6379/0
VICTUS_S3_ENDPOINT=http://seaweedfs:8333
VICTUS_S3_ACCESS_KEY=
VICTUS_S3_SECRET_KEY=
VICTUS_S3_BUCKET=victus-corpus
VICTUS_AWS_REGION=us-east-1
```

Runtime config:

- `.env` is loaded by `src/config.py`
- `config.yaml` owns pipeline defaults

## First Run

```bash
victus-processing data-layout create
victus-processing --help
```

## Quick Validation

```bash
victus-processing metadata --help
victus-processing claims --help
victus-processing bridge --help
victus-bridge --help
./.venv/bin/python -m pytest tests/test_cli_smoke.py -q
```
