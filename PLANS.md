# PLANS.md

## Goal

Hacer que el dominio `analytics` quede autocontenido dentro de `analytics/`, con su propio `AGENTS.md`, sus propios defaults de datos bajo `analytics/data`, y con los artifacts analytics existentes movidos fuera de `data/`.

## Scope

- Crear `analytics/AGENTS.md` con objetivos, fronteras y responsabilidades del futuro repo analytics.
- Crear un modulo de paths para analytics desacoplado de los outputs bajo `data/`.
- Cambiar scripts y CLI de analytics para que escriban en `analytics/data`.
- Mover artifacts analytics existentes desde `data/corpus_info/pre_ingestion_topics` y exports analytics legibles hacia `analytics/data`.
- Ajustar referencias de pipeline que consumen outputs analytics, especialmente el modo `undercovered-topics` de `metadata seed-dois`.
- Actualizar tests de defaults/rutas.

## Non-goals

- No mover artifacts operativos del pipeline como metadata, PDFs, docling o claims fuera de `data/`.
- No romper el flujo principal del pipeline ni el comando `metadata seed-dois --mode undercovered-topics`.
- No migrar inputs del pipeline que siguen siendo fuente de verdad del core, como `doi_pdf_relations.csv`, salvo que hoy sean claramente outputs analytics.

## Assumptions

- Los outputs analytics deben vivir en `analytics/data`, pero pueden seguir leyendo metadata y stage outputs del pipeline desde `data/`.
- El workspace `pre_ingestion_topics` pasa a ser propiedad de analytics y debe salir de `data/corpus_info/pre_ingestion_topics`.
- La main CLI puede depender de paths analytics para el modo `undercovered-topics` mientras siga existiendo este monorepo.

## Steps

1. Inventariar outputs analytics existentes en `data/` y decidir cuáles mover.
2. Crear `analytics/paths.py` y `analytics/AGENTS.md`.
3. Cambiar defaults de analytics CLI/scripts y del seed generator que consume pre-ingestion.
4. Mover artifacts existentes a `analytics/data`.
5. Ajustar tests de defaults/help/contratos.
6. Validar CLIs y pytest focalizado.

## Validation

- Run `python analytics/cli.py --help`
- Run `python analytics/cli.py pre-ingestion --help`
- Run `python ops/scripts/cli.py metadata seed-dois --help`
- Run `./.venv/bin/python -m pytest tests/test_analytics_cli_smoke.py tests/test_pre_ingestion_topics.py tests/test_metadata_csv_script.py tests/test_pipeline_conversion_rates_script.py tests/test_cli_smoke.py -q`

## Risks

- `metadata seed-dois --mode undercovered-topics` puede quedar apuntando a rutas viejas si no se actualizan sus defaults.
- Mover artifacts reales del workspace puede romper referencias ad hoc del usuario fuera de la CLI.
- El pipeline y analytics comparten `src/config.py`; si no se introduce una capa local de paths en analytics, el corte seguirá incompleto.

## Decision Notes

- Mantener inputs de pipeline en `data/` y outputs analytics en `analytics/data` es el corte mínimo seguro.
- La carpeta `analytics/data/pre_ingestion_topics` pasa a ser la nueva fuente por defecto para audit, draft topics y seeds orientados a gaps.

## Goal

Separar las capacidades de analytics/export/reporting de la CLI principal del pipeline y crear en root una CLI autocontenida para ese dominio, manteniendo la main CLI enfocada en etapas operativas del pipeline.

## Scope

- Identificar los comandos que hoy son analytics o pre-analytics y sacarlos de `src/cli.py`.
- Crear una nueva CLI en root con entrypoint propio para analytics.
- Reubicar o encapsular scripts de reporting/pre-ingestion analytics bajo una superficie coherente.
- Mantener la CLI principal con los flujos fundamentales: `data-layout`, `metadata explore`, `metadata seed-dois`, `bib generate`, `pdfs normalize`, `pipeline run`, `pipeline single-paper`, `claims extract`.
- Actualizar tests de ayuda/routing para ambas CLIs.

## Non-goals

- No mover `metadata explore`, `pdfs normalize`, `pipeline`, `claims`, `bib`, ni `data-layout` fuera de la main CLI.
- No rediseñar la logica interna de exports/reportes.
- No crear todavia el repositorio externo de analytics; solo preparar el corte local y autocontenido.
- No limpiar codepaths viejos no relacionados salvo dejarlos documentados.

## Assumptions

- "Analytics" incluye al menos: `metadata export-csv`, `pre-ingestion *`, `report conversion-rates`, y scripts de export CSV/reporting que hoy viven en `ops/scripts/reporting/`.
- La nueva CLI debe quedar en root con su propio entrypoint visible y no escondida dentro de `ops/scripts/`.
- La main CLI debe seguir siendo runnable desde `ops/scripts/cli.py`.

## Steps

1. Definir frontera exacta entre main CLI y analytics CLI.
2. Diseñar estructura de archivos para nueva CLI analytics sin romper imports existentes.
3. Mover el routing de analytics fuera de `src/cli.py` y apuntarlo a la nueva CLI.
4. Ajustar tests y ayudas para reflejar la división.
5. Validar ambas CLIs y revisar restos muertos o referencias obsoletas.

## Validation

- Run `python ops/scripts/cli.py --help`
- Run `python ops/scripts/cli.py metadata --help`
- Run `python ops/scripts/cli.py claims --help`
- Run `<new-analytics-cli> --help`
- Run `./.venv/bin/python -m pytest tests/test_cli_smoke.py tests/test_pre_ingestion_topics.py tests/test_metadata_csv_script.py tests/test_pipeline_conversion_rates_script.py -q`

## Risks

- La frontera entre "pipeline" y "analytics" puede quedar ambigua si `pre-ingestion` se usa operativamente para alimentar `metadata seed-dois`.
- Scripts de reporting hoy están mezclados con defaults de `src/config.py`; un corte incompleto puede dejar dependencias cruzadas.
- Tests de smoke actuales asumen una sola CLI con toda la taxonomía.

## Decision Notes

- Primera propuesta de corte: main CLI conserva solo ejecución de pipeline; analytics CLI absorbe exports CSV, pre-ingestion workspace y conversion reports.
- Mantener wrappers finos alrededor de scripts existentes reduce riesgo antes de cualquier refactor interno más profundo.

## Goal

Simplificar `metadata seed-dois` para que la CLI exponga solo dos modos semanticos y use defaults internos/configurados para cada estrategia.

## Scope

- Mantener `metadata seed-dois` como unico punto de entrada para generar seeds.
- Exponer `--mode broad-nutrition|undercovered-topics`.
- Quitar flags operativas del subcomando y retirar `gap-seed-dois` de la ayuda CLI.
- Reusar los scripts actuales `generate_metadata_seed_dois.py` y `generate_metadata_gap_seed_dois.py`.

## Non-goals

- No cambiar la logica interna de generacion de seeds.
- No eliminar los scripts operativos existentes en `ops/scripts/`.
- No rediseñar archivos de config ni formatos de output.

## Assumptions

- Los defaults actuales de rutas y umbrales ya son suficientes para uso normal.
- El usuario quiere una CLI mas simple; la configuracion avanzada queda en archivos/scripts, no en flags del subcomando.

## Steps

1. Registrar tarea y localizar referencias a `gap-seed-dois` y flags de `seed-dois`.
2. Cambiar `src/cli.py` para que `metadata seed-dois` despache por modo a uno de los dos scripts.
3. Retirar `gap-seed-dois` del parser y limpiar ayudas.
4. Ajustar tests de smoke y routing.
5. Ejecutar ayudas CLI y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py metadata --help`
- Run `python ops/scripts/cli.py metadata seed-dois --help`
- Run `./.venv/bin/python -m pytest tests/test_cli_smoke.py -q`

## Risks

- Automatizaciones que invocaban `metadata gap-seed-dois` por CLI tendran que pasar a `metadata seed-dois --mode undercovered-topics`.
- La configuracion avanzada ya no sera visible desde `--help`; queda implícita en scripts/config.

## Goal

Renombrar los modos visibles de `metadata explore` para que la CLI exprese con claridad el criterio de seleccion sin cambiar el flujo interno.

## Scope

- Exponer `broad-nutrition` en lugar de `nutrition-rag`.
- Exponer `undercovered-topics` en lugar de `gap-rag`.
- Mantener intactos los prompts, la logica de seleccion y el destino especial de descartados para el modo de gaps.
- Ajustar tests y textos de ayuda.

## Non-goals

- No separar colas de seed DOIs.
- No cambiar prompts ni comportamiento de seleccion.
- No migrar artifacts historicos ya escritos con `gap-rag`.

## Assumptions

- El renombre es de interfaz publica de CLI y helpers internos de stages/prompts; la semantica debe quedar igual.
- Conservar `gap-rag` como etiqueta persistida en artifacts evita mezclar este cambio con una migracion de datos.

## Steps

1. Registrar tarea y localizar referencias a los nombres viejos.
2. Cambiar parser CLI y dispatch de stages al nuevo naming.
3. Aceptar nuevos nombres en prompts/flows sin tocar criterio ni outputs persistidos.
4. Actualizar tests de ayuda y routing.
5. Ejecutar ayudas CLI y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py metadata --help`
- Run `python ops/scripts/cli.py metadata explore --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_metadata_selection.py tests/test_gap_discarded_audit_script.py -q`

## Risks

- Si se cambia tambien el valor persistido en `selection.mode`, se mezclaria renombre de CLI con migracion de datos historicos.
- Si algun caller externo depende de los nombres viejos del modo, necesitara adaptarse.

## Goal

Eliminar la creacion implicita de carpetas del runtime para que el proyecto no haga bootstrap global del layout al ejecutar comandos normales.

## Scope

- Quitar llamadas a `ctx.ensure_dirs()` de flows y scripts que hoy crean el arbol completo sin que haga falta.
- Eliminar `mkdir(...)` ejecutados al importar `src/tools/citation_exploration.py`.
- Mantener solo creaciones puntuales de directorio cuando un comando realmente escribe su archivo de salida, y conservar `create-data-layout` como via explicita.

## Non-goals

- No eliminar el script `create-data-layout`.
- No impedir que comandos de escritura creen el directorio padre exacto de su output.
- No rediseñar el layout de `data/`.

## Assumptions

- La "feature" que se quiere retirar es el bootstrap global e implicito del layout, no la capacidad de escribir outputs cuando el usuario ejecuta un comando productor.
- Si un flujo necesita un directorio de salida concreto, debe crearlo localmente en el punto de escritura y no mediante un barrido global.

## Steps

1. Registrar la tarea y localizar todas las rutas de creacion implicita.
2. Quitar `ctx.ensure_dirs()` de flows/scripts y `mkdir` en import-time de `citation_exploration`.
3. Ajustar tests para cubrir que importar metadata/citation flows ya no cree carpetas.
4. Ejecutar validaciones CLI y pytest focalizado.

## Validation

- Run `./.venv/bin/python ops/scripts/cli.py --help`
- Run `./.venv/bin/python ops/scripts/cli.py metadata --help`
- Run `./.venv/bin/python -m pytest tests/test_cli_smoke.py tests/test_config_loader.py tests/test_metadata_selection.py tests/test_scripts_contracts.py -q`

## Risks

- Si algun flujo dependia silenciosamente del bootstrap global, puede empezar a fallar hasta que cree solo su output real.
- La exploracion de metadata puede requerir crear directorios justo antes de guardar artifacts; eso debe seguir ocurriendo de forma localizada.

## Goal

Permitir generar un `.bib` nuevo a partir de `data/analytics/missing_pdf_items.csv`, reutilizando el comando `bib` existente como entrada alternativa al flujo basado en metadata JSON.

## Scope

- Extender `src/tools/bibliography.py` para leer un CSV con columnas como `doi`, `title` y `date`.
- Agregar un flag `--input-csv` al subcomando `bib` y al flujo interactivo relacionado.
- Cubrir el contrato con tests de generación y ayuda CLI.

## Non-goals

- No reemplazar el flujo actual `metadata -> papers.bib`; debe seguir funcionando igual.
- No enriquecer el `.bib` con datos externos ni resolver autores faltantes desde APIs.
- No cambiar el formato de `missing_pdf_items.csv`.

## Assumptions

- `missing_pdf_items.csv` trae al menos `doi` y `title` por fila; `date` puede usarse para inferir `year`.
- Cuando el origen es CSV, conviene escribir por defecto un `.bib` vecino al archivo fuente para no sobreescribir `papers.bib`.

## Steps

1. Registrar la tarea y revisar el flujo actual de `bib`.
2. Agregar parsing CSV y conversion a entradas BibTeX en `src/tools/bibliography.py`.
3. Exponer `--input-csv` en `src/cli.py` y ajustar el menu interactivo.
4. Agregar tests focalizados para contrato y help.
5. Ejecutar ayudas CLI y pytest relevante.

## Validation

- Run `python ops/scripts/cli.py bib --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_scripts_contracts.py -q`

## Risks

- El CSV no incluye autores, asi que algunas entradas BibTeX quedaran con `author = {}` y citekeys derivados del identificador interno.
- Si `date` viene malformado, el `year` quedara vacio; eso no debe bloquear la exportacion.

## Goal

Hacer que la normalizacion de nombres de PDFs use `doi_pdf_relations*.csv` como mecanismo principal desde la CLI, dejando el matching antiguo por metadata/bib fuera del flujo interactivo principal.

## Scope

- Agregar un flujo explicito de normalizacion desde `doi_pdf_relations*.csv`.
- Cambiar `normalize-pdfs` en la CLI para usar ese flujo por defecto.
- Ajustar labels, ayudas y tests para reflejar el cambio.

## Non-goals

- No eliminar las utilidades internas de matching por metadata/bib si siguen sirviendo como soporte o compatibilidad.
- No cambiar el formato de `doi_pdf_relations*.csv`.
- No refactorizar etapas de Docling o claims.

## Assumptions

- El CSV `doi_pdf_relations*.csv` en `data/analytics/` es la fuente mas confiable para mapear nombre de archivo PDF a DOI canonico.
- Mantener el comando `normalize-pdfs` evita romper a quien ya usa la CLI, aunque cambie su estrategia interna.

## Steps

1. Registrar la tarea y revisar el flujo actual de normalizacion.
2. Agregar una ruta relations-first explicita en `src/tools/pdf_normalization.py`.
3. Conectar `src/stages/pdfs.py` y `src/cli.py` para usar ese flujo en `normalize-pdfs`.
4. Agregar un script operativo en `ops/scripts/` y actualizar tests/ayudas.
5. Ejecutar ayudas CLI y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py normalize-pdfs --help`
- Run `python ops/scripts/normalize_pdfs_from_relations.py --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_scripts_contracts.py -q`

## Risks

- Si falta `doi_pdf_relations*.csv`, el comando ahora fallara antes en vez de intentar resolver por metadata/bib silenciosamente.
- Algunos PDFs antes resolubles por heuristica textual podrian quedar omitidos si no existen en relations; eso es consistente con el cambio pedido pero reduce tolerancia.

## Goal

Retirar el export pobre de claims desde la CLI y convertir el export de metadata en el CSV canonico `metadata.csv`, incluyendo `doi` junto con los demas campos utiles para analytics y bootstrap.

## Scope

- Eliminar el comando y script `claims-csv` / `export_claims_csv.py`.
- Cambiar `export_metadata_citations_csv.py` para exportar `metadata.csv` con al menos `doi`, `title` y `citation_count`.
- Actualizar referencias de CLI, ayudas, tests y scripts que hoy apuntan a `metadata_citations.csv`.

## Non-goals

- No rediseñar el schema de claims JSON ni enriquecer claims analytics en esta tarea.
- No cambiar la logica de ranking tematico mas alla de adaptar su input al nuevo CSV de metadata.
- No tocar los artifacts existentes del usuario fuera del codigo y tests.

## Assumptions

- El CSV de metadata debe seguir sirviendo como insumo para bootstrap tematico, por eso mantiene `title` y `citation_count`.
- El nombre canonico deseado pasa a ser `metadata.csv` en lugar de `metadata_citations.csv`.

## Steps

1. Registrar la tarea y localizar scripts, comandos y tests afectados.
2. Retirar `claims-csv` de la CLI y borrar su script/test dedicado.
3. Ajustar el export de metadata para incluir `doi` y escribir `metadata.csv`.
4. Actualizar referencias downstream y tests focalizados.
5. Ejecutar validaciones de CLI y pytest relevante.

## Validation

- Run `python ops/scripts/cli.py --help`
- Run `python ops/scripts/cli.py metadata-csv --help`
- Run `python ops/scripts/draft_topics_from_metadata_citations.py --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_config_loader.py tests/test_pre_ingestion_topics.py -q`

## Risks

- Cambiar el nombre del CSV canonico puede romper automatizaciones externas si dependian de `metadata_citations.csv`.
- El script de bootstrap conserva un nombre historico aunque el input pase a ser `metadata.csv`; eso queda como deuda de naming si no se quiere ampliar mas el cambio.

## Goal

Desactivar la creacion automatica de carpetas al iniciar la CLI y dejar la preparacion del layout de `data/` como una opcion explicita dentro del menu de scripts y como subcomando dedicado.

## Scope

- Quitar la llamada implicita a `ctx.ensure_dirs()` al entrar a los menus interactivos.
- Exponer el script `ops/scripts/create_data_layout.py` desde la CLI principal y desde `scripts-menu`.
- Ajustar tests de humo de CLI para cubrir el cambio de comportamiento.

## Non-goals

- No cambiar los flujos de stages que crean directorios cuando realmente ejecutan trabajo.
- No modificar el layout canonico ni la logica de `create_data_layout.py`.
- No refactorizar otros comandos de la CLI fuera de lo necesario para este cambio.

## Assumptions

- "Al iniciar la CLI" se refiere al arranque del menu principal y del menu de scripts, no a la ejecucion explicita de comandos que necesitan escribir artifacts.
- Mantener `create_data_layout.py` como script operativo existente es suficiente; solo falta hacerlo accesible de forma explicita.

## Steps

1. Registrar la tarea en `TASKS.md` y este plan antes de editar codigo.
2. Quitar el bootstrap implicito de directorios en `src/cli.py`.
3. Agregar una opcion explicita `create-data-layout` al parser y al menu de scripts.
4. Ajustar tests de `tests/test_cli_smoke.py` para validar el nuevo comportamiento.
5. Ejecutar las ayudas CLI relevantes y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py --help`
- Run `python ops/scripts/cli.py scripts-menu --help`
- Run `python ops/scripts/cli.py create-data-layout --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_config_loader.py -q`

## Risks

- Si algun flujo dependia accidentalmente de que el menu interactivo preparara carpetas antes de correr scripts, ahora necesitara invocar la opcion explicita o depender del comando concreto que ya crea sus directorios.

## Goal

Absorber en la normalizacion actual los nombres de PDFs heredados de una pasada previa `pdf_retrieval -> normalized_pdfs`, especialmente los que quedaron con sufijo `__from-raw-pdf-YYYY-MM-DD`.

## Scope

- Limpiar sufijos de procedencia heredados antes del matching por `doi_pdf_relations*.csv`, metadata o bib.
- Mantener intacta la interfaz publica del comando `normalize-pdfs`.
- Cubrir el caso con una prueba focalizada del contrato de normalizacion.

## Non-goals

- No hacer matching difuso amplio ni introducir nuevas fuentes de verdad externas.
- No reescribir el flujo completo de normalizacion.
- No intentar resolver PDFs que realmente no tengan correspondencia en relations/metadata/bib.

## Assumptions

- El sufijo `__from-raw-pdf-YYYY-MM-DD` fue agregado por una pasada operativa previa y no forma parte del titulo real.
- Remover ese sufijo antes del matching permite recuperar PDFs hoy omitidos sin aumentar ambiguedad de forma relevante.

## Steps

1. Registrar la tarea y auditar un batch real de `pdf_retrieval` para confirmar el patron.
2. Agregar limpieza del sufijo heredado en `src/tools/pdf_normalization.py`.
3. Añadir un test que verifique que `normalize-pdfs` resuelve esos nombres heredados.
4. Ejecutar ayudas CLI y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py normalize-pdfs --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_scripts_contracts.py -q`

## Risks

- Si en el futuro aparece un titulo legitimo que termine exactamente con ese patron, se limpiaria para matching; es un riesgo bajo frente al beneficio de absorber artifacts heredados.

## Goal

Guardar en una carpeta canonica separada los PDFs que `normalize-pdfs` no consigue mapear a ningun DOI.

## Scope

- Definir la ruta del directorio de PDFs no mapeados en config.
- Hacer que la normalizacion por `doi_pdf_relations*.csv` copie ahi los PDFs omitidos.
- Reflejar la ruta en la salida del flujo y cubrir el comportamiento con tests.

## Non-goals

- No reintentar matching adicional ni introducir heuristicas nuevas.
- No mover ni borrar los PDFs originales del workspace de `pdf_retrieval`.
- No cambiar la fuente de verdad actual basada en `doi_pdf_relations*.csv`.

## Assumptions

- El usuario quiere conservar los PDFs no mapeados como un artifact operativo visible, aunque sigan contando como omitidos del set normalizado.
- Una carpeta hermana de `02_normalized_pdfs` bajo `data/stages/` mantiene el layout claro del pipeline.

## Steps

1. Registrar la tarea y ubicar la ruta canonica en config.
2. Extender el flujo de normalizacion para copiar PDFs no mapeados a esa carpeta.
3. Ajustar tests de config y contrato del script.
4. Ejecutar ayudas CLI y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py normalize-pdfs --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_scripts_contracts.py tests/test_config_loader.py -q`

## Risks

- Si dos PDFs no mapeados tienen el mismo nombre base, el ultimo `copy2` sobrescribira al anterior en la carpeta destino; eso replica el comportamiento actual de copias normalizadas.

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

- Run `python ops/scripts/cli.py --help`
- Run `python ops/scripts/cli.py metadata --help`
- Run `python ops/scripts/cli.py claims --help`
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
4. Expose the new command from `ops/scripts/cli.py` and the scripts menu.
5. Generate the example CSV and add a markdown plan for manual YAML curation.
6. Add focused tests and run the relevant validations.

## Validation

- Run `python ops/scripts/cli.py --help`
- Run `python ops/scripts/cli.py draft-topics-from-citations --help`
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

- Run `python ops/scripts/cli.py --help`
- Run `python ops/scripts/cli.py pre-ingestion-topics --help`
- Run `python ops/scripts/cli.py draft-topics-from-citations --help`
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
- Run `python ops/scripts/cli.py metadata --help`

## Risks

- Marcar un seed `404` como completado evita reintentos automaticos; si Semantic Scholar lo indexa despues, habria que reinsertarlo manualmente en `seed_dois.txt`.
- Si el fix toca tambien el flujo interactivo, los tests deben dejar claro que el cambio es solo de persistencia de estado, no de seleccion.

## Goal

Retirar el script obsoleto `refilter_metadata_with_paper_selector.py` y limpiar el repositorio de referencias o tests que dependan de ese flujo retroactivo.

## Scope

- Borrar `ops/scripts/refilter_metadata_with_paper_selector.py`.
- Borrar `tests/test_refilter_metadata_script.py`.
- Confirmar que no queden ayudas, contratos o referencias activas al script eliminado.

## Non-goals

- No cambiar el flujo vigente de `metadata_selection` dentro de `citation_exploration`.
- No eliminar `paper_selector.py`, porque sigue siendo usado por el flujo actual de exploracion.
- No tocar artifacts historicos ya generados en `data/runtime/`.

## Assumptions

- El refilter retroactivo ya fue aplicado sobre el corpus y no se va a reutilizar.
- No hay una entrada CLI canónica ni documentación operativa vigente que dependa hoy de ese script.

## Steps

1. Registrar la tarea en `TASKS.md` y esta seccion del plan antes de editar codigo.
2. Borrar el script y su test dedicado.
3. Buscar referencias residuales y ajustar solo si alguna sigue apuntando al flujo eliminado.
4. Ejecutar validaciones focalizadas para confirmar que la eliminacion no rompe contratos activos.

## Validation

- Run `rg -n "refilter_metadata_with_paper_selector|test_refilter_metadata_script" .`
- Run `python -m pytest tests/test_config_loader.py tests/test_scripts_contracts.py tests/test_metadata_selection.py -q`

## Risks

- Puede quedar algun artifact historico en `data/runtime/` con el nombre viejo, pero eso no afecta el codigo si ya no hay referencias activas.
- Si alguien dependia del script como herramienta manual fuera del flujo canonico, tendra que recuperarlo desde git history.

## Goal

Crear `data/corpus_info/` y mover el workspace de `pre_ingestion_topics` bajo esa carpeta sin romper el codigo que hoy consume esas rutas.

## Scope

- Centralizar los defaults de pre-ingestion en `data/corpus_info/pre_ingestion_topics`.
- Mantener los nombres de constantes ya usados por scripts, CLI y tests.
- Ajustar mensajes y tests focalizados que todavía apunten a rutas viejas.

## Non-goals

- No cambiar la logica funcional de pre-ingestion topics.
- No mover automaticamente datos historicos fuera de lo necesario para crear la nueva estructura.
- No reorganizar otros workspaces de corpus todavia.

## Assumptions

- `pre_ingestion_topics` debe quedar agrupado bajo un contenedor nuevo de informacion de corpus.
- La compatibilidad se preserva mejor cambiando solo la resolucion centralizada de paths.

## Steps

1. Registrar la tarea en `TASKS.md` y esta seccion del plan.
2. Cambiar en `src/config.py` las rutas por defecto de pre-ingestion para que apunten a `data/corpus_info/pre_ingestion_topics`.
3. Ajustar textos/tests focalizados que verifiquen paths viejos.
4. Crear la carpeta nueva en `data/` y correr validaciones focalizadas.

## Validation

- Run `python ops/scripts/cli.py --help`
- Run `./.venv/bin/python -m pytest tests/test_config_loader.py tests/test_cli_smoke.py tests/test_pre_ingestion_topics.py -q`

## Risks

- Si hay datos locales en las rutas viejas, el codigo no los migrara automaticamente.
- Puede quedar documentacion historica en `PLANS.md` mencionando rutas previas; eso no afecta el runtime.

## Goal

Alinear la validacion de `claims_extraction` con el schema actual de `claims_v2_` para que el pipeline de claims no falle cuando el modelo responda siguiendo el prompt vigente.

## Scope

- Actualizar `validate_claims()` para exigir el schema nuevo exportado por `src/prompts/claims_v2_.py`.
- Mantener el resto del flujo de extraccion sin refactors no relacionados.
- Agregar una prueba focalizada del contrato del schema aceptado y de la incompatibilidad con el schema viejo.

## Non-goals

- No rediseñar el prompt de claims otra vez.
- No cambiar la logica de seleccion de claims, scoring, ni escritura de artifacts.

## Goal

Depurar `data/csv/pre_ingestion_topics/draft_topics.yaml` para que funcione como una base tematica mas limpia, interpretable y util para entender el corpus antes de seguir ampliando topics manualmente.

## Scope

- Curar los topics existentes para reemplazar keywords ruidosos por terminos canonicos y aliases cortos.
- Mantener el archivo en formato simple compatible con `pre_ingestion_topic_audit.py`.
- Reejecutar el audit para medir cobertura y revisar que gaps tematicos siguen visibles.

## Non-goals

- No cambiar la logica Python de matching ni la estructura del schema YAML.
- No intentar cubrir todo el corpus en una sola iteracion.
- No agregar nuevas dimensiones complejas como pesos, exclusiones o subtopics todavia.

## Assumptions

- Para esta iteracion, mejorar interpretabilidad del diccionario es mas importante que maximizar cobertura bruta.
- El usuario agregara despues topics adicionales especificos a partir de la nueva base.

## Steps

1. Registrar la tarea antes de editar el diccionario.
2. Reemplazar keywords bootstrap ruidosos por vocabulario canonico y sinonimos utiles en `draft_topics.yaml`.
3. Ejecutar de nuevo el audit pre-ingestion con el YAML curado.
4. Revisar cobertura, topicos dominantes y terminos no mapeados para confirmar la nueva base.

## Validation

- Run `python ops/scripts/pre_ingestion_topic_audit.py --input data/csv/pre_ingestion_topics/papers.csv --topics data/csv/pre_ingestion_topics/draft_topics.yaml`

## Risks

- Al hacer keywords mas estrictos, la cobertura puede bajar un poco aunque la señal mejore.
- Algunos conceptos frecuentes seguiran fuera hasta que se agreguen topics nuevos por dominio.

## Goal

Sacar la configuracion editable de pre-ingestion topics fuera de `src/tools/pre_ingestion_topics.py`, mover el `draft_topics.yaml` activo a `data/pre_ingestion_topics/`, y dejar las reglas de bootstrap en un YAML editable dentro de ese mismo workspace.

## Scope

- Agregar rutas centralizadas para el workspace editable de pre-ingestion bajo `data/pre_ingestion_topics/`.
- Externalizar las reglas automáticas hoy hardcodeadas en Python a un YAML validado en runtime.
- Hacer que el comando `draft-topics-from-citations` escriba por defecto el `draft_topics.yaml` en el workspace editable.
- Mantener `papers.csv` y `audit/` bajo `data/csv/pre_ingestion_topics/`.

## Non-goals

- No cambiar la logica de matching del audit.
- No mover `papers.csv` ni los artefactos de audit fuera de `data/csv/`.
- No rediseñar el schema del diccionario de topics usado por el audit.

## Assumptions

- El usuario quiere editar rapido las reglas y el draft, no necesariamente todos los outputs generados.
- `data/pre_ingestion_topics/` debe actuar como workspace manual durable y legible.

## Steps

1. Registrar la tarea antes de tocar rutas o codigo.
2. Agregar nuevas constantes en `src/config.py` para el workspace editable y el YAML de bootstrap.
3. Reemplazar los defaults hardcodeados por lectura desde YAML en `src/tools/pre_ingestion_topics.py`.
4. Actualizar tests y README de `data/pre_ingestion_topics/`.
5. Ejecutar ayudas CLI y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py draft-topics-from-citations --help`
- Run `python ops/scripts/cli.py pre-ingestion-topics --help`
- Run `python -m pytest tests/test_config_loader.py tests/test_cli_smoke.py tests/test_pre_ingestion_topics.py -q`

## Risks

- Cambiar el path por defecto del draft puede sorprender si alguien sigue mirando `data/csv/pre_ingestion_topics/draft_topics.yaml`.
- Si el YAML de bootstrap queda invalido, el comando de generacion fallara en runtime.
- No refactorizar consumidores ajenos a `claims_extraction` si no dependen de los campos viejos.

## Assumptions

- `src/prompts/__init__.py` sigue exportando `claims_v2_` como prompt canonico.
- El output esperado del modelo ya no incluye `claim_type`, `condition`, `effect_size` ni `comparator_arm`.

## Steps

1. Registrar la tarea y confirmar el desalineamiento exacto entre prompt y validador.
2. Cambiar `validate_claims()` al contrato nuevo, incluyendo los campos agregados por `claims_v2_`.
3. Agregar pruebas focalizadas para aceptar el schema v2 y rechazar el viejo incompleto.
4. Ejecutar pytest focalizado sobre contratos/scripts.

## Validation

- Run `python -m pytest tests/test_scripts_contracts.py -q`

## Risks

- Si existe un consumidor externo no cubierto por tests que aun produzca o espere el schema viejo, quedara incompatible hasta migrarlo.
- Como el validador solo garantiza presencia/tipos basicos, algunos errores semanticos de contenido siguen dependiendo del prompt y del modelo.

## Goal

Hacer que los seed DOIs explorados queden registrados en `explored_seed_dois.txt` y salgan de `seed_dois.txt` para que la cola editable se vacie sola a medida que se completa.

## Scope

- Ajustar la persistencia de seeds completados en `src/tools/citation_exploration.py`.
- Mantener la normalizacion actual de DOI y el archivo de completados existente.
- Agregar tests focalizados del contrato de mover un seed de la cola editable al archivo de completados.

## Non-goals

- No cambiar la logica de seleccion keep/drop.
- No cambiar el formato de `seed_dois.txt` ni `explored_seed_dois.txt` fuera de remover el DOI completado.
- No refactorizar la CLI o los stages.

## Assumptions

- `seed_dois.txt` funciona como cola editable de pendientes.
- `explored_seed_dois.txt` sigue siendo la bitacora de seeds ya procesados.
- Si un DOI ya estaba en completados, igual debe poder retirarse de `seed_dois.txt` si aun aparece ahi.

## Steps

1. Registrar la tarea en `TASKS.md` y en esta seccion del plan antes de editar codigo.
2. Extender la escritura de seeds completados para retirar el DOI normalizado desde `seed_dois.txt`.
3. Agregar tests focalizados para append + retiro de la cola editable.
4. Ejecutar pytest focalizado sobre metadata selection.

## Validation

- Run `python -m pytest tests/test_metadata_selection.py -q`

## Risks

- Reescribir `seed_dois.txt` puede remover comentarios o formato libre si se implementa de forma demasiado agresiva.
- Si alguien usa `seed_dois.txt` como historial ademas de cola, este cambio altera esa expectativa.

## Goal

Agregar un script que genere un `.txt` de DOIs candidatos para `metadata retrieval` a partir de metadata local, filtrando por un diccionario editable de keywords y priorizando por `citationCount`.

## Scope

- Leer `data/sources/metadata` como universo local de papers candidatos.
- Excluir DOIs ya presentes en `explored_seed_dois.txt`.
- Filtrar por coincidencia en title/abstract con un archivo editable de terminos semilla.
- Exportar un `.txt` con un DOI por linea, ordenado por citas descendentes.
- Exponer el script via `ops/scripts/cli.py` con un subcomando dedicado.

## Non-goals

- No consultar APIs externas.
- No usar LLMs ni embeddings.
- No modificar automaticamente `seed_dois.txt` salvo que el usuario lo pida con `--output`.

## Assumptions

- La metadata local ya contiene `doi`, `title`, `abstract` y `citationCount` suficientes para rankear.
- Un diccionario editable con raices como `diet`, `macronutrient`, `micronutrient`, `protein` sirve como primer filtro util.
- Para terminos de una palabra conviene matching por prefijo de token para capturar variantes como `dietary`.

## Steps

1. Registrar la tarea y revisar artefactos reutilizables de metadata/citations.
2. Crear un script standalone y un archivo editable de terminos semilla por defecto.
3. Exponer el comando en la CLI wrapper.
4. Agregar tests focalizados del filtrado, exclusion de explored y output.
5. Ejecutar ayudas CLI y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py metadata-seed-dois --help`
- Run `python -m pytest tests/test_metadata_seed_dois_script.py tests/test_cli_smoke.py -q`

## Risks

- Un diccionario muy amplio puede meter papers marginales; uno muy estrecho puede dejar afuera papers buenos.
- Matching por prefijo de token mejora recall pero puede introducir algunos falsos positivos.

## Goal

Hacer que el flujo de `metadata retrieval` persista tambien los papers padre cuando guarda un paper relacionado, sin cambiar la logica de seleccion ni ampliar el alcance de exploracion.

## Scope

- Ajustar `src/tools/citation_exploration.py` para garantizar el guardado del paper padre si existe una relacion `parent`.
- Mantener el shape canonico de metadata actual.
- Agregar tests focalizados del nuevo comportamiento.

## Non-goals

- No cambiar el criterio de keep/drop.
- No recorrer recursivamente el grafo de citations o references.
- No agregar nuevas dependencias ni cambiar paths.

## Assumptions

- Un `parent` representa un paper que debe existir como artefacto trazable en `data/sources/metadata`.
- Si el metadata del padre ya esta persistido, no se debe volver a pedir ni duplicar trabajo.

## Steps

1. Registrar la tarea y revisar el flujo actual de guardado en `citation_exploration`.
2. Agregar una verificacion previa que persista el paper padre cuando se guarda un paper con `parent`.
3. Cubrir el caso con tests unitarios y mantener compatibilidad con el merge actual de metadata.
4. Ejecutar pytest focalizado y ayudas CLI relevantes.

## Validation

- Run `python -m pytest tests/test_metadata_selection.py tests/test_cli_smoke.py -q`
- Run `python ops/scripts/cli.py metadata --help`

## Risks

- Si solo se conoce el `paperId` del padre y no su payload, podria requerirse un fetch adicional al API.
- Hay que evitar ciclos o fetch redundantes cuando el padre ya fue guardado en el mismo run.

## Goal

Agregar un modo automatico nuevo de `explore citations` orientado a cerrar gaps tematicos detectados en pre-ingestion, y generar una nueva cola `seed_dois.txt` desde los artifacts de audit usando un diccionario curado de terminos objetivo.

## Scope

- Agregar un prompt LLM separado del `nutrition-rag` actual para seleccionar papers de citas con foco en micronutrientes, nutricion clinica, ciclo vital, proteina/masa muscular, electrolitos, endocrino, malnutricion, biomarkers, alergias/intolerancias y disparities.
- Exponer ese modo como opcion nueva en el submenu interactivo de metadata y en el subcomando `metadata --mode ...`.
- Agregar un script operativo que lea artifacts de `data/csv/pre_ingestion_topics/audit`, combine esa senal con metadata local y escriba una nueva lista `seed_dois.txt`.
- Guardar el diccionario editable de terminos objetivo en `data/sources/` para que el flujo sea mantenible sin tocar Python.

## Non-goals

- No cambiar el flujo interactivo manual de seleccion paper por paper.
- No reemplazar el `nutrition-rag` existente ni cambiar su comportamiento.
- No consultar APIs nuevas para descubrir DOIs; la propuesta sale de artifacts locales y metadata ya almacenada.

## Assumptions

- `data/csv/pre_ingestion_topics/audit` ya contiene suficiente senal para identificar topics faltantes o poco cubiertos.
- El corpus local en `data/sources/metadata` tiene DOIs relacionados que todavia no fueron explorados como seeds.
- El usuario quiere regenerar la cola editable principal de seeds con esta nueva estrategia, pero manteniendo `--output` configurable.

## Steps

1. Registrar la tarea antes de editar codigo.
2. Parametrizar el selector LLM para soportar un prompt adicional de gaps tematicos sin romper `nutrition-rag`.
3. Exponer el nuevo modo en `src/stages/metadata.py` y `src/cli.py`.
4. Agregar un script para generar `seed_dois.txt` desde audit + metadata local usando un diccionario editable de terminos objetivo.
5. Agregar tests focalizados de prompt, CLI y script.
6. Ejecutar ayudas CLI y pytest focalizado.

## Validation

- Run `python ops/scripts/cli.py --help`
- Run `python ops/scripts/cli.py metadata --help`
- Run `python ops/scripts/cli.py metadata-gap-seed-dois --help`
- Run `python -m pytest tests/test_cli_smoke.py tests/test_metadata_selection.py tests/test_metadata_gap_seed_dois_script.py -q`

## Risks

- Si el prompt nuevo queda demasiado amplio, puede aceptar citas fuera de los gaps reales; por eso debe ser mas estricto que el `nutrition-rag`.
- Si el script usa solo matching textual simple, algunos gaps con sinonimos no incluidos en el diccionario quedaran subrepresentados.
- Sobrescribir `seed_dois.txt` puede desplazar seeds actuales; el output debe ser explicito y configurable.

## Goal

Separar los descartados generados por `gap-rag` en un bucket auditable por fecha, migrar los creados hoy a ese bucket, y preservar esa misma separacion para todos los descartados futuros de ese modo.

## Scope

- Cambiar `citation_exploration` para que `save_discarded()` escriba los descartados de `gap-rag` en una carpeta dedicada por fecha.
- Mantener compatibilidad de lectura para que el pipeline siga detectando como ya procesados tanto descartados viejos como nuevos.
- Agregar un script operativo para mover los descartados `gap-rag` creados hoy desde la carpeta legacy al bucket nuevo.
- Cubrir el comportamiento con tests focalizados.

## Non-goals

- No re-clasificar retrospectivamente todos los descartados historicos ambiguos.
- No mover automaticamente descartados de otros modos como `nutrition-rag` o `interactive`.
- No refactorizar el resto del flujo de metadata fuera de lo necesario para esta trazabilidad.

## Assumptions

- El criterio "creados hoy" se toma desde el timestamp de archivo en disco.
- Los descartados `gap-rag` recientes ya incluyen `selection.mode = "gap-rag"` y eso permite migrarlos de forma segura.
- Una carpeta por fecha bajo `discarded_papers/gap-rag/` mejora auditoria sin romper el uso operativo.

## Steps

1. Registrar la tarea antes de editar codigo.
2. Ajustar el calculo de paths de descartados para soportar bucket legacy y bucket `gap-rag` por fecha.
3. Cambiar `save_discarded()` y los checks de estado para escribir y leer ambos buckets.
4. Agregar un script para mover descartados `gap-rag` creados hoy al bucket dedicado.
5. Agregar tests focalizados del nuevo bucket y del script.
6. Ejecutar pytest focalizado y correr la migracion de hoy.

## Validation

- Run `python ops/scripts/cli.py --help`
- Run `python -m pytest tests/test_metadata_selection.py tests/test_gap_discarded_audit_script.py -q`
- Run `python ops/scripts/audit_gap_rag_discarded_today.py`

## Risks

- Si un descartado fue escrito hoy pero luego se toca otra vez, el mtime puede contaminar la nocion de "creado hoy".
- Si algun descartado viejo de `gap-rag` ya existe en ambos buckets, la resolucion de estado debe seguir siendo idempotente.

## Goal

Reparar las rutas rotas que dejo la reorganizacion manual de `data/`, haciendo que el runtime y la documentacion corta apunten al layout real actual.

## Scope

- Actualizar `config.yaml` con las rutas reales de seeds, metadata, descartados, registry, raw PDFs y testing.
- Actualizar los fallbacks canónicos en `src/config.py` para que coincidan con ese layout.
- Ajustar textos y tests focalizados que siguen validando rutas viejas.

## Non-goals

- No mover otra vez el corpus ni renombrar carpetas adicionales.
- No cambiar la logica funcional de stages o scripts.
- No limpiar artifacts historicos fuera de lo necesario para que el runtime vuelva a funcionar.

## Assumptions

- `data/stages/01_metadata` es ahora la metadata canónica activa.
- `data/corpus_info/metadata_rules` concentra seeds, diccionarios, descartados y registry.
- `data/corpus_info/pdf_retrieval/raw_pdfs` es el origen operativo actual de PDFs crudos.
- `data/archive/testing_1` es el workspace de testing que existe hoy en disco.

## Steps

1. Registrar la tarea y confirmar el layout actual bajo `data/`.
2. Alinear `config.yaml` y `src/config.py` con las rutas reales.
3. Ajustar tests y ayudas que siguen apuntando a rutas antiguas.
4. Validar con ayudas CLI y pytest focalizado.

## Validation

- Run `./.venv/bin/python ops/scripts/cli.py --help`
- Run `./.venv/bin/python ops/scripts/cli.py metadata --help`
- Run `./.venv/bin/python ops/scripts/cli.py claims --help`
- Run `./.venv/bin/python -m pytest tests/test_config_loader.py tests/test_cli_smoke.py tests/test_metadata_selection.py tests/test_scripts_contracts.py -q`

## Risks

- Si algun script externo sigue usando rutas viejas, necesitará actualizarse manualmente.
- Apuntar testing a `data/archive/testing_1` mantiene compatibilidad con el layout actual, pero deja ese flujo sobre una carpeta archivada.

## Goal

Reemplazar la CLI interactiva basada en menús por una CLI profesional orientada a subcomandos y flags, con ayudas claras, defaults visibles y documentación alineada con el flujo canónico del pipeline.

## Scope

- Retirar `menu`, `scripts-menu` y la navegación por `input()` de `src/cli.py`.
- Convertir las acciones hoy escondidas en submenús en subcomandos explícitos y consistentes.
- Revisar nombres, argumentos y ayudas para que cada subcomando exponga su intención, entradas, salidas y defaults.
- Documentar las flags y la nueva forma de uso en la documentación breve del repo.
- Actualizar tests de humo y contratos de CLI para reflejar el modelo no interactivo.

## Non-goals

- No rediseñar la lógica interna de stages o scripts salvo lo necesario para exponerlos bien en CLI.
- No cambiar el flujo canónico del pipeline ni sus rutas por defecto sin una razón de claridad fuerte.
- No introducir dependencias nuevas para frameworks de CLI.

## Assumptions

- La CLI debe seguir entrando por `ops/scripts/cli.py`.
- `argparse` es suficiente; no hace falta migrar a Typer o Click.
- La exploración de metadata puede seguir teniendo modo `interactive` internamente, pero el acceso desde CLI debe ser por flags/subcomandos y no por menús.

## Steps

1. Auditar la superficie actual de `src/cli.py` y clasificar qué opciones de menú deben convertirse en subcomandos de primer nivel o en grupos lógicos.
2. Diseñar una taxonomía estable de comandos, por ejemplo `metadata ...`, `pdfs ...`, `claims ...`, `pre-ingestion ...`, `report ...`, `data-layout ...`, sin romper más de lo necesario los flujos existentes.
3. Reescribir `build_parser()` y `main()` para que toda acción se ejecute por subcomandos con flags explícitas y ayuda útil; eliminar helpers exclusivos de menú.
4. Ajustar o extraer wrappers para que las acciones actualmente guiadas por prompts tengan equivalentes no interactivos claros.
5. Actualizar tests de CLI y documentación mínima de uso.
6. Validar `--help` global, `--help` por grupo/subcomando y pruebas focalizadas.

## Validation

- Run `UV_CACHE_DIR=/tmp/uv-cache uv run python ops/scripts/cli.py --help`
- Run `UV_CACHE_DIR=/tmp/uv-cache uv run python ops/scripts/cli.py metadata --help`
- Run `UV_CACHE_DIR=/tmp/uv-cache uv run python ops/scripts/cli.py claims --help`
- Run `UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest tests/test_cli_smoke.py tests/test_scripts_contracts.py tests/test_metadata_selection.py -q`

## Risks

- Cambiar nombres o jerarquía de comandos puede romper hábitos y automatizaciones existentes.
- Algunas rutas hoy “cómodas” del menú pueden requerir decisiones de diseño para no proliferar subcomandos redundantes.
- El modo `interactive` de metadata/claims puede necesitar una política explícita: conservarlo como flag avanzada o retirarlo del todo.

## Goal

Migrar el proyecto a un flujo de instalacion gestionado por `uv`, dejando las dependencias en `pyproject.toml`, fijando `torch` a wheels CPU-only y eliminando `requirements.txt`.

## Scope

- Declarar las dependencias de runtime del repo en `[project.dependencies]`.
- Mover `pytest` a un grupo de desarrollo nativo de `uv`.
- Configurar un índice explícito de PyTorch CPU para `torch`.
- Eliminar `requirements.txt`.
- Intentar sincronizar el entorno con `uv`.

## Non-goals

- No refactorizar el codigo de runtime para cambiar imports o arquitectura.
- No introducir Poetry, PDM ni otro gestor adicional.
- No tocar archivos no relacionados del arbol ya modificado.

## Assumptions

- El repo se ejecutará en adelante con `uv`, no con `pip install -r requirements.txt`.
- `docling` seguirá necesitando `torch`, pero basta con resolver la variante CPU.
- `uv` puede instalar `torch` desde un índice explícito si se declara en `tool.uv`.

## Steps

1. Registrar la tarea y revisar el `pyproject.toml` actual.
2. Mover dependencias a `pyproject.toml` y configurar `tool.uv` para `torch` CPU-only.
3. Eliminar `requirements.txt`.
4. Intentar `uv sync` usando una caché escribible y capturar cualquier bloqueo adicional.

## Validation

- Run `UV_CACHE_DIR=/tmp/uv-cache uv sync`
- Run `.venv/bin/python ops/scripts/cli.py --help`
- Run `.venv/bin/python -m pytest tests/test_cli_smoke.py -q`

## Risks

- Si el índice CPU de PyTorch no resuelve desde el entorno actual, `uv sync` seguirá bloqueado por red.
- Alguna automatización externa puede seguir esperando `requirements.txt` y necesitará actualizarse.
