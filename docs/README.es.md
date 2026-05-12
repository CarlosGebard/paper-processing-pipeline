# Victus Processing

Pipeline para convertir papers científicos en metadata, PDFs normalizados, artefactos Docling y claims.

## Qué Resuelve

- busca candidatos en Semantic Scholar
- guarda metadata canónica
- normaliza PDFs crudos
- procesa PDFs con Docling y heurísticas locales
- extrae claims con modelos OpenAI
- expone bridge para registry, storage y eventos Victus

## Uso Local

```bash
uv sync
victus-processing --help
victus-processing data-layout create
```

Flujo principal:

```bash
victus-processing metadata explore --mode broad-nutrition
victus-processing pdfs normalize
victus-processing pipeline run
victus-processing claims extract --skip-existing
```

## Validar

```bash
victus-processing --help
victus-processing metadata --help
victus-processing claims --help
./.venv/bin/python -m pytest tests/test_cli_smoke.py -q
```

La suite completa aún referencia `analytics/`, que está saliendo del repo.

## Leer Más

- [Setup](setup.md)
- [Arquitectura](architecture.md)
- [Contratos](contracts.md)
- [Operación](operations.md)
- [Seguridad](security.md)
- [Tests](tests.md)
- [Roadmap](roadmap.md)
- [CLI local](../ops/scripts/local/README.md)
- [CLI bridge](../ops/scripts/bridge/README.md)
