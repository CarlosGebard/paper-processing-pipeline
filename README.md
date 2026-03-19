# Paper Processing Pipeline

Pipeline para procesar papers científicos desde exploración de metadata hasta extracción final de claims con LLM.

## Resumen del flujo

1. Exploras metadata y construyes tu base de papers (`metadata`).
2. Generas archivo `.bib` desde metadata (`bib`).
3. Usas **Zotero** (externo) para recuperar PDFs usando ese `.bib`.
4. Copias/mueves esos PDFs al proyecto (`raw_pdf`).
5. Ejecutas Docling + Heuristics (`pipeline`).
6. Como paso final, ejecutas `llm_to_claim.py` sobre secciones METHODS/RESULTS.

## Estructura base de rutas (fuente de verdad)

Las rutas se controlan desde `config.yaml`.

Valores actuales:
- `storage.papers_dir`: `data/metadata`
- `storage.discarded_dir`: `data/discarded_papers`
- `storage.registry_dir`: `data/registry`
- `storage.raw_pdf_dir`: `data/raw_pdf`
- `docling_ingestion.input_dir`: `data/input_pdfs`
- `docling_ingestion.json_dir`: `data/docling_extraction/json`
- `docling_ingestion.markdown_dir`: `data/docling_extraction/markdown`
- `heuristics.full_dir`: `data/post_heuristics/full_doc`
- `heuristics.final_dir`: `data/post_heuristics/final`

## Requisitos

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Para desarrollo del módulo heurístico:

```bash
pip install -e ./scripts/heuristics_model[dev]
```

## Configuración de credenciales

No guardes credenciales reales en `config.yaml`. Usa variables de entorno o un archivo `.env` local.

Variables esperadas:
- `SEMANTIC_SCHOLAR_API_KEY`
- `OPENAI_API_KEY`

Ejemplo:

```bash
cp .env.example .env
```

## Uso recomendado paso a paso

### 1) Explorar y guardar metadata

Opción interactiva:
```bash
python main.py menu
```
Selecciona opción `1`.

O directo:
```bash
python main.py metadata
```

Salida principal esperada:
- Metadata JSON en `data/metadata`
- Descartados en `data/discarded_papers`

### 2) Generar `.bib`

```bash
python main.py bib
```

Salida esperada:
- `data/metadata/papers.bib`

También puedes definir archivo destino:
```bash
python main.py bib --output /ruta/salida/papers.bib
```

### 3) Retrieval de PDFs en Zotero (externo)

1. Importa `papers.bib` en Zotero.
2. Ejecuta tu flujo de retrieval de PDFs dentro de Zotero.
3. Exporta/copia los PDFs descargados al directorio `data/raw_pdf`.

Notas:
- Pueden venir con nombres no normalizados; el pipeline los intenta mapear por DOI/título usando metadata + `.bib`.

### 4) Ejecutar Docling + Heuristics

```bash
python main.py pipeline
```

Con OCR activado:
```bash
python main.py pipeline --enable-ocr
```

Qué hace internamente:
1. Normaliza/sincroniza PDFs desde `data/raw_pdf` hacia `data/input_pdfs`.
2. Corre Docling por cada PDF y produce:
   - JSON en `data/docling_extraction/json`
   - Markdown en `data/docling_extraction/markdown`
3. Corre Heuristics sobre el Markdown y produce:
   - Documento completo en `data/post_heuristics/full_doc`
   - Markdown final estructurado en `data/post_heuristics/final`

### 4b) Ejecutar flujo completo hasta claims

```bash
python main.py process-all
```

Qué hace:
1. Sincroniza `data/raw_pdf` hacia `data/input_pdfs`.
2. Salta documentos ya completos hasta `data/claims`.
3. Reusa artefactos intermedios existentes si Docling o Heuristics ya fueron generados.
4. Intenta extraer claims solo para documentos que todavía no tienen salida final.

Notas:
- Si un paper no expone suficientes secciones útiles en `heuristics.final.md`, la etapa `claims` se omite.
- La extracción de claims requiere conectividad y credenciales válidas para OpenAI.

### 5) Paso final: `llm_to_claim`

Este paso no está integrado aún al `main.py`; se ejecuta como script.

```bash
python scripts/llm_to_claim.py \
  --methods /ruta/methods.md \
  --results /ruta/results.md \
  --output /ruta/claims.json \
  --model gpt-5-mini \
  --max-claims 10
```

Requisitos para este paso:
- Variable `OPENAI_API_KEY` configurada.
- Archivos de entrada separados para METHODS y RESULTS en markdown.

## Comandos útiles

Normalizar PDFs manualmente (sin correr todo el pipeline):
```bash
python main.py normalize-pdfs
```

Abrir menú interactivo:
```bash
python main.py menu
```

Procesar todo hasta claims:
```bash
python main.py process-all
```

## Validación para desarrollo

Smoke checks:

```bash
python main.py --help
python main.py metadata --help
python main.py claims --help
```

Tests:

```bash
python -m pytest tests -q
python -m pytest scripts/heuristics_model/tests -q
```

## Política de datos versionados

En este repositorio, `data/` mezcla working set y outputs del pipeline.

Se considera razonable mantener como material fuente o de referencia:
- `data/metadata`
- `data/discarded_papers`
- `data/registry`

Se consideran outputs/runtime y no deberían versionarse por defecto:
- `data/raw_pdf`
- `data/input_pdfs`
- `data/docling_extraction`
- `data/post_heuristics`
- `data/claims`
- `data/next_batch`

## Estado actual del pipeline

- `main.py` es el CLI principal para:
  - exploración de metadata
  - generación de `.bib`
  - normalización de PDFs
  - Docling + Heuristics
- El retrieval de PDFs ocurre fuera del proyecto en Zotero.
- `llm_to_claim.py` es el último paso y se corre aparte.
