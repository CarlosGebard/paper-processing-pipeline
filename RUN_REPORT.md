# Pipeline Run Report

Date: 2026-03-18

## Goal

Process the newly added PDFs from `data/raw_pdf` through the pipeline, add a non-reprocessing mechanism for documents already completed through `claims`, and record the results.

## System changes applied first

- Added `python main.py process-all` to run `raw_pdf -> input_pdfs -> docling -> heuristics -> claims`.
- Added persistent artifact stage tracking in `data/registry/documents.jsonl`.
- The pipeline now skips documents already completed through `claims`.
- The pipeline now reuses existing Docling and Heuristics outputs instead of recomputing them unnecessarily.
- Claim extraction now skips files whose `.claims.json` already exists.
- PDF normalization now handles truncated author/year filenames more reliably.

## Input observed in `data/raw_pdf`

- `Tang et al. - 2019 - Intestinal microbiota in cardiovascular health and disease JACC state-of-the-art review..pdf`
- `Tasali et al. - 2022 - Effect of sleep extension on objectively assessed energy intake among adults with overweight in real.pdf`
- `Teasdale et al. - 2019 - Dietary intake of people with severe mental illness systematic review and meta-analysis.pdf`
- `Venter et al. - 2020 - Nutrition and the immune system a complicated tango.pdf`

An older already-completed paper was also present:
- `Sun and Empie - 2012 - Fructose metabolism in humans – what isotopic tracer studies tell us.pdf`

## Outcome by document

### Completed through claims

- `Teasdale et al. - 2019`
  - normalized to `07998f36868fae0cba82f55f36114d3c5b8765f2__doi-10.1192-bjp.2019.20`
  - reached `data/claims`
  - produced 11 claims

- `Tasali et al. - 2022`
  - normalized to `3cf2f082f3edb72438f84042801bfb7f1989cba8__doi-10.1001-jamainternmed.2021.8098`
  - reached `data/claims`
  - produced 6 claims

- `Sun and Empie - 2012`
  - already had `claims`
  - was skipped correctly as complete

### Completed through heuristics but blocked before claims

- `Tang et al. - 2019`
  - normalized to `20c8aa3490fd1a6a6f424209f6af46729d6b8b09__doi-10.1016-j.jacc.2019.03.024`
  - reached `data/post_heuristics/final`
  - claim extraction skipped because Methods and Results were both missing in the final structured markdown

- `Venter et al. - 2020`
  - normalized to `cc53cbb79b97ea374dde4b219bdc06b51f5566a2__doi-10.3390-nu12030818`
  - reached `data/post_heuristics/final`
  - claim extraction skipped because Methods, Results, and Abstract were not recoverable in the final structured markdown

## Files generated or updated

### New/updated final markdown

- `data/post_heuristics/final/07998f36868fae0cba82f55f36114d3c5b8765f2__doi-10.1192-bjp.2019.20.heuristics.final.md`
- `data/post_heuristics/final/20c8aa3490fd1a6a6f424209f6af46729d6b8b09__doi-10.1016-j.jacc.2019.03.024.heuristics.final.md`
- `data/post_heuristics/final/3cf2f082f3edb72438f84042801bfb7f1989cba8__doi-10.1001-jamainternmed.2021.8098.heuristics.final.md`
- `data/post_heuristics/final/cc53cbb79b97ea374dde4b219bdc06b51f5566a2__doi-10.3390-nu12030818.heuristics.final.md`

### New claim files

- `data/claims/07998f36868fae0cba82f55f36114d3c5b8765f2__doi-10.1192-bjp.2019.20.claims.json`
- `data/claims/3cf2f082f3edb72438f84042801bfb7f1989cba8__doi-10.1001-jamainternmed.2021.8098.claims.json`

## Validation performed

```bash
python -m pytest tests -q
python -m pytest scripts/heuristics_model/tests -q
python main.py process-all --help
./.venv/bin/python main.py claims --input data/post_heuristics/final --output data/claims
```

## Remaining issues

- `Tang` and `Venter` need better section recovery upstream if you want them to reach `claims`.
- The claim stage requires network access and valid OpenAI credentials.
- The long-running Docling conversions did complete, but they are slow enough that batch runs may appear silent for a while.
