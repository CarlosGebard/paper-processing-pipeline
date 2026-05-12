# Contracts

## Local CLI

Entrypoint:

```bash
victus-processing
```

Path fallback:

```bash
python ops/scripts/local/cli.py
```

Public command groups:

- `metadata`
- `bib`
- `pdfs`
- `pipeline`
- `claims`
- `bridge`
- `data-layout`

Stable validation commands:

```bash
victus-processing --help
victus-processing metadata --help
victus-processing claims --help
victus-processing bridge --help
victus-bridge --help
```

## Storage Paths

Defaults come from `config.yaml`.

| Purpose | Default path |
|---|---|
| metadata | `data/stages/01_metadata` |
| raw PDFs | `data/corpus_info/pdf_retrieval/downloaded_pdfs` |
| unmatched PDFs | `data/corpus_info/pdf_retrieval/unmatched_pdf` |
| normalized PDFs | `data/stages/02_normalized_pdfs` |
| Docling + heuristics | `data/stages/03_docling_heuristics` |
| claims | `data/stages/04_claims` |
| testing | `data/archive/testing_1` |

## Env Vars

Pipeline:

- `SEMANTIC_SCHOLAR_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_METADATA_SELECTION_MODEL`

Bridge:

- `VICTUS_PG_DSN`
- `VICTUS_REDIS_URL`
- `VICTUS_S3_ENDPOINT`
- `VICTUS_S3_ACCESS_KEY`
- `VICTUS_S3_SECRET_KEY`
- `VICTUS_S3_BUCKET`
- `VICTUS_AWS_REGION`

## Bridge Events

Event prefix:

- input `artifact:done` publishes as `victus:artifact:done`
- already-prefixed `victus:*` values are preserved

Reserved events:

- `victus:artifact:done`
- `victus:stage:started`
- `victus:stage:done`
- `victus:error`

Bridge payloads include `timestamp`. Payloads tied to a paper include `id`.

## Bridge Storage

Default bucket:

```text
victus-corpus
```

Paper prefix:

```text
papers/{paper_id}/
```

Raw PDF object key:

```text
papers/{paper_id}/raw/source.pdf
```

## Bridge Registry

Expected table: `paper_registry`.

Fields read or written:

- `paper_id`
- `doi`
- `s3_prefix`
- `status_proc`
- `status_rag`
- `last_event`

Known statuses:

- processing: `pending`, `processing`, `completed`, `failed`
- RAG: `pending`, `indexed`, `error`
