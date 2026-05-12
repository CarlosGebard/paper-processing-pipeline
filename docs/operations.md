# Operations

## Daily Commands

Help:

```bash
victus-processing --help
```

Create data layout:

```bash
victus-processing data-layout create
```

Generate metadata from one DOI:

```bash
victus-processing metadata from-doi --doi 10.1000/demo
```

Normalize PDFs:

```bash
victus-processing pdfs normalize
```

Run Docling and heuristics:

```bash
victus-processing pipeline run
```

Extract claims:

```bash
victus-processing claims extract --skip-existing
```

Single-paper test:

```bash
victus-processing pipeline single-paper --doi 10.1000/demo
```

## Bridge Commands

```bash
victus-processing bridge ingest-pdf ./paper.pdf --doi 10.xxxx/yyyy
victus-processing bridge status sha256_hash
victus-processing bridge stage-start sha256_hash --stage processing
victus-processing bridge stage-done sha256_hash --stage processing
```

## Logs

No central logging system is defined in this repo. CLI output goes to stdout/stderr.

## Deploy

No deploy workflow is defined in this repo.

## Troubleshooting

- Missing `OPENAI_API_KEY`: claims and LLM selection commands fail.
- Missing `SEMANTIC_SCHOLAR_API_KEY`: Semantic Scholar commands may still run, but rate limits may be stricter.
- Missing bridge env vars: `bridge` commands fail before touching services.
- `pytest tests -q` fails on `analytics/`: analytics is being removed from this repo.

## Before Commit Or Push

```bash
victus-processing --help
victus-processing metadata --help
victus-processing claims --help
victus-processing bridge --help
victus-bridge --help
./.venv/bin/python -m pytest tests/test_cli_smoke.py -q
```

Check tree:

```bash
git status --short
```

## Rollback

No migration tool is defined. Basic rollback is git-based:

```bash
git status --short
git restore --staged <path>
git restore <path>
```

Do not rollback user data under `data/` unless explicitly intended.
