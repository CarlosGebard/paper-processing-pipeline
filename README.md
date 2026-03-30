# Paper Processing Pipeline

This repository turns a curated set of scientific papers into structured artifacts and claim-level outputs.

It starts with metadata discovery, moves through PDF normalization and Docling-based parsing, and ends with LLM-assisted claim extraction. The design is intentionally stage-based, so each step leaves inspectable artifacts on disk instead of hiding everything behind a single black box run.

## What It Does

- explores candidate papers from Semantic Scholar
- stores accepted metadata locally
- generates a `.bib` file from stored metadata
- normalizes PDFs into a pipeline-friendly naming scheme
- converts PDFs into structured JSON with Docling
- filters and routes relevant sections
- extracts empirical health-related claims with LLM models

## Pipeline At A Glance

The canonical flow is:

1. `metadata`
2. `bib`
3. `raw_pdf`
4. `input_pdfs`
5. `docling + heuristics + llm_sections`
6. `claims`

In practice, that means:

1. Review candidate papers and keep the ones you want.
2. Export a bibliography file from saved metadata.
3. Place retrieved PDFs in the raw PDF stage.
4. Normalize filenames into the traceable pipeline format.
5. Run Docling and section filtering to produce final structured documents.
6. Generate claim JSON files from the final section bundles.

## Why The Naming Looks Strict

The pipeline preserves traceability through names like:

`document_id__doi-10.3390-nu12102983`

That base name is reused across PDFs, intermediate JSON outputs, registry entries, and claims files. It makes it much easier to understand where an artifact came from and to resume partial runs safely.

### 2. Configure credentials

Create a local `.env` file in the repository root when you need API-backed stages.

## Configuration

Runtime paths are controlled through `config.yaml` and resolved through `config_loader.py`.

Current stage roots are:

- metadata: `data/sources/metadata`
- discarded: `data/sources/discarded_papers`
- registry: `data/sources/registry`
- csv exports and csv reference files: `data/csv`
- raw PDFs: `data/stages/01_raw_pdf`
- normalized PDFs: `data/stages/02_input_pdfs`
- Docling and heuristics bundles: `data/stages/03_docling_heuristics`
- claims: `data/stages/04_claims`

If you need to move storage locations, change them in `config.yaml` instead of hardcoding paths elsewhere.

To create the canonical `data/` directory layout without moving or deleting existing files:

```bash
python ops/scripts/create_data_layout.py
```
