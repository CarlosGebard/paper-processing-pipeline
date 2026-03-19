# Heuristics Model

Deterministic post-processing over Docling markdown for section normalization, classification, and rendering.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ./scripts/heuristics_model[dev]
pytest scripts/heuristics_model/tests -q
```
