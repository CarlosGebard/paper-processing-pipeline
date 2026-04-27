# Paper Processing Pipeline ([Español](README.es.md))

Pipeline for turning scientific papers into structured metadata, document artifacts, and claim-level outputs.

The repository is organized around command-line workflows for the operational pipeline, from paper discovery through Docling, heuristics, and claims extraction.

## What It Does

- explores candidate papers from Semantic Scholar
- stores accepted metadata locally
- generates a `.bib` file from saved metadata
- normalizes PDFs into DOI-first names
- converts PDFs into structured JSON with Docling
- applies heuristics to produce `final.json`
- extracts empirical health-related claims with LLM models

## Canonical Flow

```text
metadata
-> bib
-> raw_pdf
-> input_pdfs
-> docling + heuristics + llm_sections
-> claims
```

## Main CLI

Entry point:

```bash
python ops/scripts/cli.py
```

### `data-layout create`

Creates the canonical directory structure under `data/`.

```bash
python ops/scripts/cli.py data-layout create
```

### `metadata explore --mode broad-nutrition`

Explores candidates from Semantic Scholar and uses an LLM to keep papers with a broad nutrition focus.

```bash
python ops/scripts/cli.py metadata explore --mode broad-nutrition
```

### `metadata explore --mode undercovered-topics`

Explores candidates from Semantic Scholar and uses an LLM to prioritize undercovered topics.

```bash
python ops/scripts/cli.py metadata explore --mode undercovered-topics
```

### `metadata from-doi --doi ...`

Creates canonical metadata for a single DOI.

```bash
python ops/scripts/cli.py metadata from-doi --doi 10.1000/demo
```

### `metadata seed-dois --mode broad-nutrition`

Generates new general-purpose seed DOIs from local metadata.

```bash
python ops/scripts/cli.py metadata seed-dois --mode broad-nutrition
```

### `metadata seed-dois --mode undercovered-topics`

Generates seed DOIs oriented to gaps or undercovered topics.

```bash
python ops/scripts/cli.py metadata seed-dois --mode undercovered-topics
```

### `bib generate`

Generates a BibTeX file from local metadata.

```bash
python ops/scripts/cli.py bib generate
```

It can also use an auxiliary CSV source:

```bash
python ops/scripts/cli.py bib generate --input-csv data/analytics/missing_pdf_items.csv
```

### `pdfs normalize`

Normalizes or copies raw PDFs into DOI-first names for the pipeline.

```bash
python ops/scripts/cli.py pdfs normalize
```

### `pipeline run`

Runs Docling and heuristics over normalized PDFs and produces `final.json`.

```bash
python ops/scripts/cli.py pipeline run
```

### `pipeline single-paper --doi ...`

Processes a single DOI end to end through claims in the testing workspace.

```bash
python ops/scripts/cli.py pipeline single-paper --doi 10.1000/demo
```

### `claims extract`

Extracts claims with an LLM from `final.json` into `claims.json`.

```bash
python ops/scripts/cli.py claims extract
python ops/scripts/cli.py claims extract --skip-existing
```

Useful flags:

- `--input`: input file or directory
- `--output`: output file or directory
- `--model`: claim extraction model
- `--max-claims`: override the maximum number of claims
- `--temperature`: model temperature
- `--pattern`: glob used when input is a directory
- `--auto-approve-under-7000-tokens`: auto-process smaller inputs
- `--skip-existing`: skip existing claim outputs

## Data Layout

Main paths:

- metadata: `data/stages/01_metadata`
- raw PDFs: `data/corpus_info/pdf_retrieval/downloaded_pdfs`
- normalized PDFs: `data/stages/02_normalized_pdfs`
- Docling + heuristics: `data/stages/03_docling_heuristics`
- claims: `data/stages/04_claims`
- testing: `data/archive/testing_1`

Runtime paths are resolved from:

- `src/config.py`
- `config.yaml`
- `.env`

## Configuration

Main configuration file:

- `config.yaml`

Local overrides and secrets:

- `.env`

Typical uses:

- API credentials
- default models
- storage path overrides

## Minimal Run

Bootstrap:

```bash
python ops/scripts/cli.py data-layout create
```

Main flow:

```bash
python ops/scripts/cli.py metadata explore --mode broad-nutrition
python ops/scripts/cli.py pdfs normalize
python ops/scripts/cli.py pipeline run
python ops/scripts/cli.py claims extract --skip-existing
```

Single-paper test flow:

```bash
python ops/scripts/cli.py pipeline single-paper --doi 10.1000/demo
```

## Validation

Useful commands:

```bash
python ops/scripts/cli.py --help
python ops/scripts/cli.py metadata --help
python ops/scripts/cli.py claims --help
python -m pytest tests -q
```

## Notes

- The pipeline preserves traceability through DOI-first names and stage-specific artifacts.
