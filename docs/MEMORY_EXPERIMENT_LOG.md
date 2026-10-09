# Bitácora — Diagnóstico de memoria WorkflowDirector

**Regla:** cada corrida de Colab genera una entrada fechada y reproducible; no mezclar mediciones de distintas versiones o flags. Guardar en esta rama y enlazar los JSONL/logs disponibles, con cuidado porque los archivos bajo /content no persisten tras desconexión. Evitar registrar identificadores personales o datos de modelos sin necesidad.

## Entrada M-000 — Arranque del frente (2026-10-08, CDMX)

**Objetivo:** caracterizar la memoria que permanece en RAM y VRAM entre trabajos independientes, para construir una frontera segura POST_A/PRE_B.
**Por qué:** las descargas agresivas crashearon Comfy/Colab; el residuo no tiene dueño identificado. Necesitamos separar modelo, caché, allocator, archivo GGUF mmap, runtime normal y Context intencional.
**Estado:** PLANIFICADO; NO se han ejecutado todavía pruebas nuevas de memoria en esta rama.

**Entorno reportado por el usuario:**
- Python 3.13.15.
- 723 paquetes Python detectados (conteo del notebook, no memoria).
- PyTorch 2.11.0+cu130.
- CUDA de PyTorch 13.0.
- GPU/Comfy frontend/flags **a revalidar** en esta sesión; entorno previamente auditado: T4, Comfy 0.39.0, frontend 1.53.10, `--cache-none`.

**Trabajos realizados por el asistente en GitHub (sin tocar el Colab del usuario):**
- Rama `feature/memory-diagnostics` desde `feature/colab-acceptance`.
- Investigación y selección escalonada: baseline externa → ProfilerX pinned → diagnóstico dirigido con snapshots/weakrefs.
- Observador externo read-only `scripts/memory_watch.py` + regresiones.
- Runbook reproducible `docs/MEMORY_COLAB_RUNBOOK.md`.
- Plan/handoff `docs/MEMORY_WORKSTREAM_2026-10-08.md`.
- PR #7 draft. PR #6 de Context permanece pausado.

**No realizado:** no se ha instalado ProfilerX, no se ha ejecutado el observador en T4, no hay diagnóstico confirmado de fuga, no se ha cambiado ni limpiado RAM/VRAM.

**Siguiente acción única:** verificación D0, iniciar D1 y compartir mediciones/read-only JSONL antes de instalar ProfilerX.

## Plantilla para cada nueva entrada

### M-XXX — YYYY-MM-DD HH:MM (CDMX)
- **Pregunta/Hipótesis:** 
- **Por qué esta prueba distingue causas:** 
- **Rama, commit, versión Comfy/frontend/Python/torch/CUDA y flags:** 
- **GPU y límite de RAM runtime:** 
- **Extensiones añadidas (nombre/commit/deps), otras presentes:** 
- **Workflow A / B, configuración/semilla y `prompt_id`:** 
- **Momentos BASELINE, POST_A, PRE_B, POST_B (UTC):** 
- **RSS, PSS, Pss_Anon/File, cgroup available, PyTorch allocated/reserved, NVML used:** 
- **Picos observados y resolución temporal:** 
- **Fuente de datos (archivos JSONL, API, logs/capturas):** 
- **Resultados positivos, negativos, incertidumbre:** 
- **¿Hubo crash/timeout/interferencia/auto queue?:** 
- **¿Se verificó ausencia de efectos secundarios del profiler?:** 
- **Cambios/rollback realizados:** 
- **Conclusión: confirmado/descartado/inconcluso:** 
- **Siguiente acción concreta:** 


## Entrada M-001 — D0, verificación de arranque (2026-10-08, CDMX)

**Origen:** salida literal de la celda de inspección ejecutada por el usuario en su Colab vivo; no es una medición A/B ni una sesión de ProfilerX.

**Resultados observados:**
- Python: `3.13.15`; PyTorch instalado según metadata: `2.11.0+cu130` (sin `import torch`).
- GPU global: `Tesla T4`, driver `580.82.07`, memoria usada `105 MiB` de `15360 MiB` (consulta `nvidia-smi`, no atribución por proceso).
- ComfyUI PID: `16744`; directorio de trabajo: `/content/ComfyUI`; script de arranque: `/content/ComfyUI/main.py`.
- Argumentos significativos: `--listen 127.0.0.1 --port 8188 --reserve-vram 0.8 --preview-method taesd --cache-none`. Directorio de salida de Colab: `/content/drive/MyDrive/AI/output/26-10-08`.
- HTTP `GET /workflowdirector/health`: `ok=true`, `workflowdirector_version=0.0.7-dev`, `comfyui_version=0.39.0`, `director_service.ready=true`, `active_run_id=null`, `boundary_mode=observe-phase2-nondestructive`, `observation_window_seconds=1.0`.
- ComfyUI frontend vivo: **no verificado** en la salida D0. CUDA reportado por PyTorch en otro momento: 13.0; no leído de este proceso en D0.
- No hay medidas del RSS/PSS del proceso ni Torch allocator en esta entrada; falta ejecutar el observador externo.

**Interpretación restringida:** `--cache-none` está presente en la línea de comando real de Comfy y el backend de WorkflowDirector responde en modo no destructivo. Los 105 MiB son ocupación global puntual antes de los trabajos, no garantía de memoria libre futura ni prueba de ausencia de retención.

**Cambios hechos en Colab:** ninguno por el asistente. **ProfilerX:** no instalado por este procedimiento.

**Siguiente acción única:** iniciar el observador externo read-only `scripts/memory_watch.py` desde el checkout `feature/memory-diagnostics`, registrar idle y luego A Klein Q4 → B Klein Q6 manteniendo parámetros, IDs y fronteras POST_A/PRE_B. No hacer unload ni reinstalar Torch/CUDA.


### M-001 — Inicio del observador externo D1 (evidencia Colab enviada por el usuario)
- Revisión utilizada del auditor: `4917217d31ffa4c06154adc7d0c771fe41ce11ee`, carpeta `/content/WorkflowDirector-Memory-Audit`.
- PID de observador externo: `17492`; proceso Comfy observado: PID `16744`; estado reportado: `ACTIVO`.
- JSONL temporal: `/content/memory_20261009_045123.jsonl`. El usuario no ha exportado todavía el archivo.
- Muestras `2026-10-09T04:51:23.648159+00:00`, `04:51:25.687981`, `04:51:27.741035`, `04:51:29.779940`: Comfy RSS redondeado por el watcher a `1.26 GiB` en las cuatro; GPU global `110100480 bytes` usados (=105 MiB), `16106127360 bytes` totales (=15360 MiB).
- La salida abreviada del watcher no contiene PSS/Pss_Anon/Pss_File; deben extraerse del JSONL antes de atribuir memoria. Baseline de pocos segundos no demuestra ausencia de retención.
- **Pendiente:** ejecutar A Klein Q4 y B Klein Q6 sin plugins adicionales y correlacionar timestamps/IDs con el JSONL. No se observan ejecuciones A/B en estos datos.



### M-001 — BASELINE con smaps_rollup (usuario, 2026-10-09T04:57:58.835073Z / 2026-10-08 22:57 CDMX)

Celda `mark("BASELINE")` ejecutada durante el muestreo externo de `/content/memory_20261009_045123.jsonl`. La función tomó la **última muestra ya escrita** al momento del marcador; el timestamp exacto de esa muestra está en `sample_utc` dentro del archivo de marcas, pendiente de exportar. Datos reportados por el usuario:
- `rss_bytes`: **1.257 GiB**
- `pss_bytes`: **1.241 GiB**
- `pss_anon_bytes`: **0.719 GiB**
- `pss_file_bytes`: **0.512 GiB**
- GPU global `nvidia-smi`: **105 MiB**
- Marcador: `BASELINE` en `2026-10-09T04:57:58.835073+00:00`; archivo de markers con sufijo `_markers.jsonl`.

**Lectura preliminar, NO diagnóstico causal:** de PSS, ~0.512 GiB se asigna proporcionalmente a páginas file-backed que pueden incluir librerías, archivos mmap u otras páginas de archivo; ~0.719 GiB a páginas anónimas. El residuo PSS no desglosado corresponde potencialmente a Shmem/redondeo; no asumir que sea leak. No hay todavía corridas A/B ni datos de picos o retención después de workflows.

**Siguiente paso:** ejecutar secuencia Q4→Q6 habitual manteniendo flags/modelos y monitor externo; registrar prompt/run IDs, intervalos y marcas de POST_A/PRE_B si la orquestación permite distinguirlas, de lo contrario correlacionar por timestamps del registro nativo sin detener la ejecución.


### M-001 — POST_AB y POST_AB_SETTLED (observaciones reportadas por el usuario, 2026-10-09 UTC / 2026-10-08 CDMX)

El usuario ejecutó `mark("POST_AB")` a `2026-10-09T05:05:22.108350+00:00` y `mark("POST_AB_SETTLED")` a `2026-10-09T05:05:37.109427+00:00`; ambos marcadores leen la última muestra disponible del monitor y **no son mediciones síncronas al microsegundo del job**.

| Métrica | BASELINE | POST_AB | POST_AB_SETTLED | Cambio BASELINE→POST_AB |
|---|---:|---:|---:|---:|
| RSS proceso GiB | 1.257 | 2.829 | 2.829 | +1.572 |
| PSS proceso GiB | 1.241 | 2.813 | 2.813 | +1.572 |
| PSS anónimo GiB | 0.719 | 2.311 | 2.311 | +1.592 |
| PSS respaldado por archivos GiB | 0.512 | 0.488 | 0.488 | -0.024 |
| GPU global MiB | 105 | 189 | 189 | +84 |

**Observaciones restringidas:** el aumento de PSS se concentra en páginas anónimas, no en `Pss_File`. En las dos lecturas separadas ~15 s no se observó reducción, pero no se puede clasificar como fuga, ni como memoria no recuperable. GPU es global, no exclusivo del proceso; el aumento no identifica objetos vivos de Torch. Sin curvas de tiempo aún no conocemos picos, secuencia interna A/B ni cuándo aparece el incremento.

**Monitor:** activo según la salida del usuario; `/content/memory_20261009_045123.jsonl`; marcas `/content/memory_20261009_045123_markers.jsonl`. **Datos faltantes:** archivo JSONL completo, timestamp exacto de cada muestra, IDs/estados terminales de A/B, peak RSS/PSS/VRAM, observaciones Torch allocator antes/después. No se ha instalado ProfilerX ni se ha ejecutado cleanup por el asistente.

**Siguiente acción:** extraer picos y serie temporal de la ventana PRE_AB→POST_AB desde los archivos ya registrados, correlacionar IDs / tiempos y verificar resultado de A y B antes de ensayar ningún remedio o instalar ProfilerX.


### M-001 — Picos observados en la serie D1 (resultado reportado por el usuario)

**Fuente:** salida de la celda de análisis del observador `/content/memory_20261009_045123.jsonl`, con los marcadores de `/content/memory_20261009_045123_markers.jsonl`. Datos derivados por el usuario de **218 muestras** en el intervalo desde BASELINE a POST_AB_SETTLED. **Los workflows A y B terminaron correctamente**, sin error reportado. No se entregaron aún IDs de jobs ni el JSONL íntegro.

**Picos muestreados (cada 2 segundos; no necesariamente máximos absolutos)**:
- RSS máximo: **8.898 GiB**, `2026-10-09T05:03:28.474544+00:00`.
- PSS máximo: **8.882 GiB**, mismo timestamp.
- PSS anónima máximo: **7.138 GiB**, `2026-10-09T05:03:59.415631+00:00`.
- PSS file-backed máximo: **5.475 GiB**, `2026-10-09T05:02:51.272411+00:00`.
- GPU global máximo: **12121 MiB**, `2026-10-09T05:01:53.466667+00:00`.
- **Importante**: los máximos ocurren en instantes distintos. No sumar PSS anónima máxima + PSS file máxima ni asumir que el máximo de GPU coincidió con el de RSS.

**Evolución por minuto reportada**, formato `HH:MM:SS RSS inicial→final GiB | Pss_Anon final GiB | pico GPU global MiB`:
```
04:57:58 1.26 -> 1.26 | 0.72 |   105
04:58:58 1.26 -> 1.26 | 0.72 |   105
04:59:58 1.26 -> 4.28 | 0.88 |  3933
05:00:58 4.78 -> 3.84 | 2.39 | 12121
05:01:58 3.82 -> 2.91 | 2.38 |  9945
05:02:58 2.91 -> 8.67 | 7.14 | 12029
05:03:58 8.67 -> 2.83 | 2.31 | 12029
05:04:58 2.83 -> 2.83 | 2.31 |   189
```

**Interpretación provisional:** dos intervalos de uso intenso GPU (~12 GiB), un pico tardío de RSS/PSS del proceso (~8.9 GiB), y caída importante al estado residual RSS 2.829 / Pss_Anon 2.311 GiB. El residuo anónimo está ~1.592 GiB por encima de BASELINE, mantenido entre dos muestras a 15 segundos. No prueba fuga ni irreversibilidad. File-backed PSS alcanzó 5.475 GiB transitoriamente, así que la atribución a mmap GGUF sigue abierta para ese pico **aunque el aumento residual final sea anónimo**. Etiquetar cada intervalo A o B requiere IDs y timestamps del servicio; aun cuando el orden sea Q4→Q6, las fronteras precisas aún no están verificadas.

**Riesgo y siguiente control:** antes de repetir D1 confirmar disponibilidad de RAM del cgroup/proceso y estado idle. Repetir corrida equivalente solo si hay margen, con una marca PRE_AB_2 y POST_AB_2, y evaluar si el residuo anónimo crece de nuevo o se estabiliza; alternativamente extraer JSONL completo y timestamps de trabajos existentes antes de nuevas cargas. Evitar cleanup manual, `/free`, reinstalaciones, cambios de cache flags y ProfilerX hasta completar el baseline.


### M-001 — Análisis íntegro del ZIP recibido (524 muestras)

Se recibió el ZIP original `M001_memory_AB.zip` en la conversación (incluye traza y marcas) y se inspeccionó íntegramente sin conectar a Colab ni alterar el proceso. Documentación forense de continuidad:
**[MEMORY_M001_TRACE_ANALYSIS_2026-10-08.md](MEMORY_M001_TRACE_ANALYSIS_2026-10-08.md)**.

Resultados adicionales a las muestras puntuales anteriores:
- 524 muestras consecutivas (04:51:23–05:09:26Z), cadencia mediana 2.056 s, sin brechas >3s, PID Comfy 16744 en todas.
- Actividad intensa GPU primera 05:00:50–05:02:04Z (pico 12121 MiB) y segunda 05:02:31–05:04:08Z (pico 12029 MiB); **son bloques heurísticos, no IDs de A/B**.
- Entre ambas, VRAM global llegó a 189 MiB y RSS bajó a 2.810 GiB (05:02:06Z), luego comenzó a crecer por nuevas operaciones. El residuo final RSS 2.829 GiB es comparable; no evidencia de aumento monotónico por la segunda actividad.
- Después de 05:04:10Z hay **~5m16s de estabilidad** hasta 05:09:26Z: RSS 2.8291 GiB; PSS_Anon 2.3114 GiB; GPU global 189 MiB. Esto extiende la observación de estabilidad inicial de 15 segundos.
- Pico de file-backed PSS 5.475 GiB transitorio, distinto en tiempo del pico anónimo 7.138 GiB. Residuo final respecto al baseline: PSS_Anon +1.592 GiB, PSS_File -0.024 GiB. Memoria anónima retenida, **causa no atribuida, NO denominar fuga**.
- Ambos trabajos reportados completados correctamente. Faltan prompt/run IDs y tiempos exactos; no está probada ninguna hipótesis H1–H5.
- **Próxima prueba M-002:** verificar cgroup RAM disponible y proceso idle; repetir A→B sin reinicio ni cambios, con marcas adicionales y tiempos IDs; comprobar si el estado POST_AB vuelve ~2.829 GiB RSS / 2.311 GiB PSS_Anon o sigue aumentando. No instalar ProfilerX antes de segunda baseline.
