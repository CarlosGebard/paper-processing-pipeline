# RunPod Plan

## Objetivo

Dejar un pod de RunPod listo para que, al iniciarse, haga automaticamente lo necesario para operar este repositorio sin comandos manuales dentro del pod:

- actualizar el repo desde GitHub
- preparar el entorno Python
- iniciar la sincronizacion de carpetas con tu PC
- detectar PDFs nuevos
- moverlos a `data/stages/02_input_pdfs`
- ejecutar la pipeline
- copiar los resultados de `data/stages/03_docling_heuristics`
- devolver esos resultados a tu PC mediante la carpeta sincronizada

La operacion diaria objetivo es:

1. Encender el pod.
2. Copiar PDFs a una carpeta local sincronizada.
3. Esperar los resultados en otra carpeta local sincronizada.

## Arquitectura propuesta

### Repo en el pod

- `/workspace/paper-processing-pipeline`

Repo a usar:

- `https://github.com/CarlosGebard/paper-processing-pipeline.git`

### Carpeta sincronizada entre pod y PC

- `/workspace/shared/paper_pipeline_sync`

### Estructura del sync root

```text
/workspace/shared/paper_pipeline_sync/
├── incoming_pdfs/
├── outgoing_docling/
└── system/
    ├── processed_inputs/
    ├── failed_inputs/
    └── logs/
```

### Estructura equivalente en tu PC

```text
~/paper_pipeline_sync/
├── incoming_pdfs/
├── outgoing_docling/
└── system/
    ├── processed_inputs/
    ├── failed_inputs/
    └── logs/
```

## Flujo operativo

1. El pod arranca.
2. Un script de startup hace `git clone` o `git pull`.
3. El script prepara `.venv` e instala `requirements.txt`.
4. El script inicia Syncthing.
5. El script inicia un worker en background.
6. Tu PC sincroniza PDFs a `incoming_pdfs/`.
7. El worker mueve esos PDFs a `data/stages/02_input_pdfs`.
8. El worker ejecuta `python main.py pipeline`.
9. El worker copia la salida de `data/stages/03_docling_heuristics` a `outgoing_docling/`.
10. Syncthing devuelve esos resultados a tu PC.

## Paso a paso inicial

Esta parte se hace una sola vez.

### 1. Preparar Syncthing en tu PC

Instala Syncthing y dejalo corriendo.

Crea la carpeta local:

- `~/paper_pipeline_sync`

Crea dentro la estructura:

```text
~/paper_pipeline_sync/
├── incoming_pdfs/
├── outgoing_docling/
└── system/
    ├── processed_inputs/
    ├── failed_inputs/
    └── logs/
```

Agrega esa carpeta en Syncthing como:

- `Send & Receive`

Guarda tu `Device ID` de Syncthing porque lo necesitara el pod.

### 2. Crear el pod en RunPod

Configuralo con:

- acceso por SSH
- almacenamiento persistente en `/workspace`
- una imagen Linux con `bash`, `git` y `python3`

### 3. Subir los scripts al pod

Sube una sola vez estos scripts a:

```text
/workspace/bootstrap/runpod_startup.sh
/workspace/bootstrap/runpod_worker.sh
```

### 4. Definir variables de entorno en RunPod

Variables minimas:

```bash
REPO_URL=https://github.com/CarlosGebard/paper-processing-pipeline.git
REPO_BRANCH=main
REPO_DIR=/workspace/paper-processing-pipeline
SYNC_ROOT=/workspace/shared/paper_pipeline_sync
ST_PC_DEVICE_ID=<TU_DEVICE_ID_DE_SYNCTHING>
```

Si luego vas a correr etapas con API keys, agrega tambien las credenciales necesarias.

### 5. Configurar el startup command del pod

Usa:

```bash
bash /workspace/bootstrap/runpod_startup.sh
```

Ese comando debe ejecutarse automaticamente al arrancar el pod.

### 6. Encender el pod por primera vez

Cuando arranque:

- el repo se clonara o actualizara
- el entorno Python se preparara
- Syncthing se iniciara
- el worker quedara corriendo

### 7. Aceptar el device del pod en Syncthing de tu PC

En tu Syncthing local:

1. Acepta el nuevo dispositivo del pod.
2. Comparte con ese dispositivo la carpeta `~/paper_pipeline_sync`.

Eso se hace solo una vez.

### 8. Verificar sincronizacion inicial

Debes ver sincronizadas ambas rutas:

- `~/paper_pipeline_sync`
- `/workspace/shared/paper_pipeline_sync`

## Operacion diaria

Una vez hecha la configuracion inicial, tu rutina se reduce a esto:

### 1. Encender el pod

No deberias entrar por SSH ni correr comandos manuales.

### 2. Copiar PDFs a la carpeta local

Copia los PDFs aqui:

- `~/paper_pipeline_sync/incoming_pdfs`

### 3. Esperar la ejecucion automatica

El worker del pod hara esto solo:

1. detecta PDFs nuevos
2. los mueve a `data/stages/02_input_pdfs`
3. ejecuta `python main.py pipeline`
4. copia resultados a `outgoing_docling`
5. mueve los PDFs procesados a `system/processed_inputs`
6. manda los fallidos a `system/failed_inputs`

### 4. Leer resultados en tu PC

Los bundles generados apareceran aqui:

- `~/paper_pipeline_sync/outgoing_docling`

## Responsabilidad de cada script

### `runpod_startup.sh`

Debe:

- crear carpetas persistentes
- clonar o actualizar el repo
- crear `.venv`
- instalar dependencias
- iniciar Syncthing
- iniciar `runpod_worker.sh`

Debe ejecutarse automaticamente en cada arranque del pod.

### `runpod_worker.sh`

Debe:

- monitorear `incoming_pdfs`
- mover PDFs nuevos al repo
- ejecutar la pipeline
- copiar resultados a `outgoing_docling`
- registrar logs
- separar procesados y fallidos

Debe quedar corriendo en background.

## Estado final esperado

Cuando todo este bien configurado:

- no necesitas escribir comandos en el pod
- no necesitas correr `git pull` a mano
- no necesitas ejecutar `python main.py ...` manualmente
- solo enciendes el pod y copias PDFs a la carpeta local

## Checklist de validacion

### Validacion inicial

- el pod arranca correctamente
- `runpod_startup.sh` se ejecuta solo
- el repo aparece en `/workspace/paper-processing-pipeline`
- existe `.venv`
- Syncthing esta corriendo
- el worker esta corriendo
- la carpeta sincronizada existe en ambos lados

### Validacion funcional

1. Copiar 1 PDF a `~/paper_pipeline_sync/incoming_pdfs`
2. Esperar sincronizacion al pod
3. Verificar que el worker lo procese
4. Verificar que aparezca salida en `~/paper_pipeline_sync/outgoing_docling`

## Riesgos y limites

- La primera vez debes aceptar el device del pod en Syncthing.
- Si el pod cambia de identidad de Syncthing en cada arranque, tendras que reaceptarlo. Conviene mantener persistente su configuracion bajo `/workspace`.
- Si luego quieres incluir `claims`, el worker debera agregar la etapa correspondiente y tendra que existir la configuracion de credenciales.
- Si mezclas muchos lotes en la misma carpeta sin convencion, luego sera mas dificil separar salidas por corrida.

## Resumen corto

Primera vez:

1. Configurar Syncthing en tu PC.
2. Crear el pod.
3. Subir `runpod_startup.sh` y `runpod_worker.sh`.
4. Configurar variables del pod.
5. Poner `bash /workspace/bootstrap/runpod_startup.sh` como startup command.
6. Encender el pod.
7. Aceptar el device del pod en Syncthing.

Uso diario:

1. Encender el pod.
2. Copiar PDFs a `incoming_pdfs`.
3. Esperar resultados en `outgoing_docling`.
