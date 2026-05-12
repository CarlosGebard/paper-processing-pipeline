# Bridge CLI

Victus bridge CLI and SDK for registry, object storage, and Redis events.

Preferred command after `uv sync`:

```bash
victus-bridge --help
```

It is also mounted inside local CLI:

```bash
victus-processing bridge --help
```

Path fallback:

```bash
python ops/scripts/local/cli.py bridge --help
```

## Owns

- `paper_registry` writes and reads
- S3-compatible artifact upload/reference
- Redis event publishing
- stable bridge payload contracts

## Does Not Own

- local pipeline stages
- Docling processing
- claims extraction logic
- RAG indexing

## Commands

```bash
victus-bridge ingest-pdf ./paper.pdf --doi 10.xxxx/yyyy
victus-bridge mark-artifact-done sha256_hash --artifact-kind normalized_json --artifact-key papers/sha256_hash/stages/02_normalized/final.json
victus-bridge publish-event artifact:ready --paper-id sha256_hash --payload-json '{"artifact_kind":"normalized_json"}'
victus-bridge stage-start sha256_hash --stage processing
victus-bridge stage-done sha256_hash --stage processing
victus-bridge publish-error --service victus-service --error-type ExternalServiceTimeout --message "Connection refused" --severity critical
victus-bridge status sha256_hash
```

## Environment

```text
VICTUS_PG_DSN=
VICTUS_REDIS_URL=redis://redis:6379/0
VICTUS_S3_ENDPOINT=http://seaweedfs:8333
VICTUS_S3_ACCESS_KEY=
VICTUS_S3_SECRET_KEY=
VICTUS_S3_BUCKET=victus-corpus
VICTUS_AWS_REGION=us-east-1
```

## Validation

```bash
victus-bridge --help
victus-processing bridge --help
```
