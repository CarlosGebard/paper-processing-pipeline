# Paper Processing Pipeline ([English](README.md))

Pipeline para convertir papers científicos en metadata estructurada, artifacts de documento y salidas de claims.

El repositorio se organiza alrededor de flujos por línea de comandos para la ejecución operativa del pipeline, desde el descubrimiento de papers hasta Docling, heurísticas y extracción de claims.

## Qué Hace

- explora papers candidatos desde Semantic Scholar
- guarda metadata aceptada localmente
- genera un archivo `.bib` desde metadata guardada
- normaliza PDFs a nombres DOI-first
- convierte PDFs a JSON estructurado con Docling
- aplica heurísticas para producir `final.json`
- extrae claims empíricos relacionados con salud usando modelos LLM

## Flujo Canónico

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

Crea la estructura canónica de directorios bajo `data/`.

```bash
python ops/scripts/cli.py data-layout create
```

### `metadata explore --mode broad-nutrition`

Explora candidatos desde Semantic Scholar y usa una LLM para conservar papers con foco amplio en nutrición.

```bash
python ops/scripts/cli.py metadata explore --mode broad-nutrition
```

### `metadata explore --mode undercovered-topics`

Explora candidatos desde Semantic Scholar y usa una LLM para priorizar temas subcubiertos.

```bash
python ops/scripts/cli.py metadata explore --mode undercovered-topics
```

### `metadata from-doi --doi ...`

Crea metadata canónica para un DOI puntual.

```bash
python ops/scripts/cli.py metadata from-doi --doi 10.1000/demo
```

### `metadata seed-dois --mode broad-nutrition`

Genera nuevos seed DOIs generales desde metadata local.

```bash
python ops/scripts/cli.py metadata seed-dois --mode broad-nutrition
```

### `metadata seed-dois --mode undercovered-topics`

Genera seed DOIs orientados a gaps o temas subcubiertos.

```bash
python ops/scripts/cli.py metadata seed-dois --mode undercovered-topics
```

### `bib generate`

Genera un archivo BibTeX desde metadata local.

```bash
python ops/scripts/cli.py bib generate
```

También puede usar un CSV auxiliar:

```bash
python ops/scripts/cli.py bib generate --input-csv data/analytics/missing_pdf_items.csv
```

### `pdfs normalize`

Normaliza o copia raw PDFs a nombres DOI-first para el pipeline.

```bash
python ops/scripts/cli.py pdfs normalize
```

### `pipeline run`

Corre Docling y heurísticas sobre PDFs normalizados y produce `final.json`.

```bash
python ops/scripts/cli.py pipeline run
```

### `pipeline single-paper --doi ...`

Procesa un solo DOI de punta a punta hasta claims en el workspace de testing.

```bash
python ops/scripts/cli.py pipeline single-paper --doi 10.1000/demo
```

### `claims extract`

Extrae claims con una LLM desde `final.json` hacia `claims.json`.

```bash
python ops/scripts/cli.py claims extract
python ops/scripts/cli.py claims extract --skip-existing
```

Flags más útiles:

- `--input`: archivo o directorio de entrada
- `--output`: archivo o directorio de salida
- `--model`: modelo para extracción de claims
- `--max-claims`: override del máximo de claims
- `--temperature`: temperatura del modelo
- `--pattern`: glob usado cuando el input es directorio
- `--auto-approve-under-7000-tokens`: auto procesa inputs pequeños
- `--skip-existing`: salta outputs de claims ya existentes

## Layout De Datos

Rutas principales:

- metadata: `data/stages/01_metadata`
- raw PDFs: `data/corpus_info/pdf_retrieval/downloaded_pdfs`
- normalized PDFs: `data/stages/02_normalized_pdfs`
- Docling + heuristics: `data/stages/03_docling_heuristics`
- claims: `data/stages/04_claims`
- testing: `data/archive/testing_1`

Las rutas runtime se resuelven desde:

- `src/config.py`
- `config.yaml`
- `.env`

## Configuración

Archivo principal de configuración:

- `config.yaml`

Overrides locales y secretos:

- `.env`

Usos típicos:

- credenciales API
- modelos por defecto
- overrides de rutas de storage

## Ejecución Mínima

Bootstrap:

```bash
python ops/scripts/cli.py data-layout create
```

Flujo principal:

```bash
python ops/scripts/cli.py metadata explore --mode broad-nutrition
python ops/scripts/cli.py pdfs normalize
python ops/scripts/cli.py pipeline run
python ops/scripts/cli.py claims extract --skip-existing
```

Flujo de prueba para un solo paper:

```bash
python ops/scripts/cli.py pipeline single-paper --doi 10.1000/demo
```

## Validación

Comandos útiles:

```bash
python ops/scripts/cli.py --help
python ops/scripts/cli.py metadata --help
python ops/scripts/cli.py claims --help
python -m pytest tests -q
```

## Notas

- El pipeline preserva trazabilidad con nombres DOI-first y artifacts por etapa.
