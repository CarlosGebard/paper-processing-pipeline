# PLANS.md

## Goal

Reordenar la CLI interactiva principal para separar metadata y claims en submenus, unificar el origen de metadata en `seed_dois.txt`, y hacer configurable desde `config.yaml` el umbral de auto-aprobacion de claims.

## Scope

- Ajustar el menu principal de `main` y agregar submenus para metadata y claims.
- Hacer que metadata interactivo y metadata automatico usen `data/sources/seed_dois.txt`.
- Mantener la opcion de crear metadata para un DOI individual dentro del submenu de metadata.
- Leer el umbral de `llm_to_claim` desde `config.yaml` y usarlo en la CLI interactiva y en el subcomando `claims`.
- Retirar del menu principal la opcion de ejecutar el flujo completo hasta claims.

## Non-goals

- No reorganizar scripts-menu ni cambiar su alcance.
- No refactorizar stages o prompts fuera de lo necesario para conectar la nueva navegacion.
- No eliminar comandos CLI existentes salvo sacar la opcion interactiva del menu principal.

## Assumptions

- `data/sources/seed_dois.txt` es la fuente deseada para ambos modos de metadata.
- El flujo `nutrition-rag` sigue siendo el modo automatico via LLM.
- `single-paper` debe seguir disponible como comando CLI aunque no forme parte del submenu de claims.

## Steps

1. Registrar la tarea y revisar los puntos de entrada actuales de metadata, claims y config.
2. Mover el umbral de auto-aprobacion de claims a `config.yaml` y exponerlo en `config_loader.py`.
3. Agregar un flujo interactivo de metadata basado en `seed_dois.txt`.
4. Reordenar `paper_pipeline/cli.py` con submenus de metadata y claims y quitar la opcion de process-all del menu principal.
5. Actualizar pruebas focalizadas de config y CLI, y correr validaciones relevantes.

## Validation

- Run `python main.py --help`
- Run `python main.py metadata --help`
- Run `python main.py claims --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_config_loader.py tests/test_metadata_selection.py -q`

## Risks

- Cambiar el modo `metadata --mode interactive` puede alterar expectativas si alguien dependia del seed unico viejo.
- El nombre del flag `--auto-approve-under-7000-tokens` queda historico aunque el valor venga de config.

## Goal

Add a deterministic bootstrap flow that reads `metadata_citations.csv`, extracts weighted candidate terms from titles, exports a draft CSV under `examples/`, and documents the follow-up curation path into `topics.yaml`.

## Scope

- Add reusable candidate-term extraction helpers under `paper_pipeline/tools/`.
- Add a standalone script that reads title/citation CSV, weights terms by document frequency and citation score, and exports a ranked candidate CSV.
- Expose the script through a dedicated CLI command and scripts menu entry.
- Generate one example CSV from the current `data/csv/metadata_citations.csv` and add a short action plan for turning it into YAML.
- Add focused tests for ranking/output behavior and CLI help.

## Non-goals

- Do not auto-generate a final canonical `topics.yaml` without manual review.
- Do not use LLMs or embeddings.
- Do not add new external dependencies.

## Assumptions

- `metadata_citations.csv` contains at least `title` and `citation_count`.
- Weighted candidate extraction should stay deterministic and explainable rather than trying to auto-create final topics.

## Steps

1. Update `TASKS.md` and this plan so the change is tracked before code edits.
2. Add one candidate-extraction path that scores n-grams from titles with document frequency, total frequency, and citation-weighted support.
3. Add one CLI script for `metadata_citations.csv -> candidate_terms.csv`.
4. Expose the new command from `main.py` and the scripts menu.
5. Generate the example CSV and add a markdown plan for manual YAML curation.
6. Add focused tests and run the relevant validations.

## Validation

- Run `python main.py --help`
- Run `python main.py draft-topics-from-citations --help`
- Run `./.venv/bin/python -m pytest tests/test_cli_smoke.py tests/test_pre_ingestion_topics.py tests/test_pre_ingestion_topics_bootstrap.py -q`

## Risks

- Generic phrases from guidelines/reports can dominate rankings unless filtered explicitly.
- Citation-heavy generic papers can bias candidate terms if weighting is not capped or normalized.

## Goal

Consolidar los tests de pre-ingestion en un solo archivo para simplificar mantenimiento, manteniendo la cobertura existente y sin cambiar comportamiento del codigo productivo.

## Scope

- Unificar `tests/test_pre_ingestion_topics.py`, `tests/test_pre_ingestion_topics_script.py` y `tests/test_pre_ingestion_topics_bootstrap.py`.
- Mantener los mismos casos de prueba con nombres y agrupacion mas claros dentro de un unico archivo.
- Eliminar los archivos redundantes una vez migrado el contenido.

## Non-goals

- No cambiar la logica de `paper_pipeline/tools/pre_ingestion_topics.py`.
- No cambiar la logica de los scripts `pre_ingestion_topic_audit.py` ni `draft_topics_from_metadata_citations.py`.
- No expandir la cobertura de tests mas alla de la consolidacion.

## Assumptions

- La division actual en tres archivos responde a crecimiento incremental y no a una necesidad fuerte de separacion.
- Mantener funciones de test pequenas dentro de un solo archivo sigue dando buena legibilidad en pytest.

## Steps

1. Registrar la tarea en `TASKS.md` y esta seccion del plan antes de editar tests.
2. Mover el contenido de los tres archivos a `tests/test_pre_ingestion_topics.py` manteniendo imports y fixtures locales minimos.
3. Borrar los dos archivos ya absorbidos.
4. Ejecutar pytest focalizado sobre el archivo consolidado.

## Validation

- Run `python -m pytest tests/test_pre_ingestion_topics.py -q`

## Risks

- Puede quedar duplicacion de imports o carga repetida de scripts si la consolidacion no ordena bien el archivo.
- Un archivo unico demasiado desordenado haria mas dificil localizar fallas, por eso la agrupacion interna debe quedar clara.

## Goal

Mover los outputs por defecto de pre-ingestion a `data/csv/pre_ingestion_topics/` y agregar un script que cree la estructura canonica propuesta bajo `data/`.

## Scope

- Cambiar los defaults y constantes de pre-ingestion que hoy apuntan a `data/pre_ingestion_topics`.
- Ajustar CLI, scripts y documentacion donde se muestran esas rutas.
- Agregar un script operativo para crear la estructura base de carpetas de `data/`.
- Agregar o actualizar tests focalizados para rutas y script.

## Non-goals

- No mover archivos existentes del usuario automaticamente.
- No refactorizar otras rutas de `data/` que ya estan alineadas con `sources`, `stages`, `testing` o `csv`.
- No cambiar la logica funcional del audit o bootstrap de topics.

## Assumptions

- "adentro de .csv" se interpreta como `data/csv/`.
- El nuevo script debe ser seguro e idempotente: crear carpetas faltantes sin borrar ni mover contenido.

## Steps

1. Registrar la tarea y revisar los puntos donde `pre_ingestion_topics` se usa como default.
2. Cambiar constantes y defaults a `data/csv/pre_ingestion_topics`.
3. Agregar un script para crear la estructura canonica de `data/` usando las rutas centralizadas.
4. Actualizar README y tests focalizados.
5. Ejecutar validaciones de pytest y ayudas CLI relacionadas.

## Validation

- Run `python main.py --help`
- Run `python main.py pre-ingestion-topics --help`
- Run `python main.py draft-topics-from-citations --help`
- Run `./.venv/bin/python -m pytest tests/test_config_loader.py tests/test_cli_smoke.py tests/test_pre_ingestion_topics.py -q`

## Risks

- Al cambiar defaults, algunos mensajes de ayuda y docs pueden quedar apuntando a la ruta vieja si no se actualizan todos los puntos.
- Si el script de scaffolding usa rutas duplicadas en vez de las centralizadas, puede divergir del layout real en el futuro.

## Goal

Agregar tests focalizados para `metadata` automatico (`nutrition-rag`), confirmar por que muchos seed DOIs se saltan, y reparar el flujo para que los DOIs `404` no queden reintentandose indefinidamente.

## Scope

- Verificar el comportamiento real de `explore_with_nutrition_rag()` frente a seeds que Semantic Scholar responde con `404`.
- Ajustar el manejo de estado para que esos seeds queden cerrados en la cola editable.
- Actualizar los tests de `tests/test_metadata_selection.py` para cubrir el comportamiento reparado.

## Non-goals

- No cambiar el modelo de seleccion ni la logica de clasificacion de candidatos.
- No introducir nuevas dependencias ni persistencias operativas adicionales si no son necesarias.
- No refactorizar el flujo interactivo mas alla de mantener consistencia con el fix minimo.

## Assumptions

- Un `404` de Semantic Scholar para un seed DOI significa que hoy no hay metadata recuperable por ese proveedor.
- `data/sources/explored_seed_dois.txt` funciona como cola cerrada de seeds ya revisados, no solo de exitos.

## Steps

1. Registrar la tarea y confirmar la causa comparando seeds pendientes contra la respuesta real del endpoint.
2. Cambiar el flujo para cerrar los seeds `404` en el archivo de completados y evitar skips repetidos.
3. Ajustar o agregar tests para el comportamiento automatico y cualquier ruta hermana que comparta la misma logica.
4. Ejecutar validaciones focalizadas y, si pasan, las ayudas CLI relevantes.

## Validation

- Run `python -m pytest tests/test_metadata_selection.py -q`
- Run `python main.py metadata --help`

## Risks

- Marcar un seed `404` como completado evita reintentos automaticos; si Semantic Scholar lo indexa despues, habria que reinsertarlo manualmente en `seed_dois.txt`.
- Si el fix toca tambien el flujo interactivo, los tests deben dejar claro que el cambio es solo de persistencia de estado, no de seleccion.
