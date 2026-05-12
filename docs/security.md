# Security

## Secrets

Keep secrets in `.env` or deployment secret stores. Do not commit `.env`.

Sensitive values:

- `OPENAI_API_KEY`
- `SEMANTIC_SCHOLAR_API_KEY`
- `VICTUS_PG_DSN`
- `VICTUS_S3_ACCESS_KEY`
- `VICTUS_S3_SECRET_KEY`

## Permissions

Bridge commands can write to:

- Postgres `paper_registry`
- S3-compatible object storage
- Redis event channels

Run bridge commands only against intended environments.

## Data Risk

`data/` may contain downloaded PDFs, metadata, claims, and intermediate artifacts. Treat it as corpus data, not source code.

## Known Risks

- Redis default URL uses `redis://`; no TLS is enforced by the bridge code.
- S3 signing is implemented locally in `ops/scripts/bridge/victus_ingest_bridge/storage.py`.
- Full test suite currently includes stale `analytics/` references.
- No CI workflow exists in this repo.

## Push Checklist

```bash
git status --short
rg -n "OPENAI_API_KEY=.+|SEMANTIC_SCHOLAR_API_KEY=.+|VICTUS_S3_SECRET_KEY=.+|VICTUS_PG_DSN=.+" .
victus-processing --help
./.venv/bin/python -m pytest tests/test_cli_smoke.py -q
```

Review staged files:

```bash
git diff --cached --stat
git diff --cached
```
