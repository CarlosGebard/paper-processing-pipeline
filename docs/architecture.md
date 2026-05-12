# Architecture

## Boundary

This repo owns local paper processing:

```text
metadata -> bib -> raw_pdf -> input_pdfs -> docling + heuristics -> claims
```

This repo does not own analytics, deployment infrastructure, Qdrant, RAG indexing, or external PDF retrieval services.

## Components

- `ops/scripts/local/`: local CLI entrypoint and command routing.
- `ops/scripts/bridge/`: Victus bridge package for registry, storage, and event integration.
- `ops/scripts/*.py`: helper scripts called by the local CLI.
- `src/config.py`: config loading, `.env` loading, runtime paths.
- `src/stages/`: pipeline stage orchestration.
- `src/tools/`: supporting tools for bibliography, metadata, PDFs, and claims.
- `src/docling_heuristics_pipeline/`: Docling and heuristic document processing.
- `tests/`: validation.

## Data Flow

```text
data/corpus_info/metadata_rules
  -> data/stages/01_metadata
  -> data/corpus_info/pdf_retrieval/downloaded_pdfs
  -> data/stages/02_normalized_pdfs
  -> data/stages/03_docling_heuristics
  -> data/stages/04_claims
```

## CLI Shape

```bash
python ops/scripts/local/cli.py metadata --help
python ops/scripts/local/cli.py pdfs --help
python ops/scripts/local/cli.py pipeline --help
python ops/scripts/local/cli.py claims --help
python ops/scripts/local/cli.py bridge --help
```

`ops/scripts/local/commands.py` owns commands, flags, handlers, and parser construction.

`src/config.py` stays outside CLI because it is shared runtime state for CLI, stages, tools, and helper scripts.
