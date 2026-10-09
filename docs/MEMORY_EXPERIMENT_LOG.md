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


### M-002 — preflight para repetición A→B, aún SIN ejecutar (2026-10-08 ~23:19 CDMX)

Salida reportada del Colab del usuario:
- `/proc/meminfo`: `MemTotal = 12.67 GiB`, `MemAvailable = 8.78 GiB`.
- `/sys/fs/cgroup/memory.current = 0.47 GiB` y `memory.max = max`; no usar esta cifra como representación válida del proceso Comfy dado que contradice el RSS anterior (~2.829 GiB). Falta identificar el cgroup correspondiente al PID Comfy.
- `GET /workflowdirector/health`: `ready=True`, `active_run_id=None` (idle).
- `WATCH_PROC` activo al verificar; archivo previo `/content/memory_20261009_045123.jsonl`; monitor anterior tiene límite de 1800 s y puede expirar durante una segunda corrida.
- Comando `nvidia-smi` devolvió `returncode=0`, pero el usuario **no mostró sus valores** en la salida; VRAM actual no confirmada en este preflight.
- No se han realizado nuevos unloads, instalaciones ni reinicios en este reporte.

**Decisión:** conservar el log original; iniciar una nueva captura externa M-002 antes del trabajo, verificar VRAM/health y memoria disponible de nuevo justo antes de A/B; si las condiciones cambian, no ejecutar. Marcar PRE_AB_2 / POST_AB_2 / POST_AB_2_SETTLED, usar los workflows originales sin modificación y anotar IDs nativos. Este registro es preparación, NO un resultado de M-002.


### M-002 — POST_AB_2 y POST_AB_2_SETTLED (datos Colab, 2026-10-09 UTC / 2026-10-08 CDMX)

Salida de la celda `mark_m002` suministrada por el usuario; **no se aportaron aún PRE_AB_2, IDs/estados de A y B, ni la traza M-002 completa**:

| Métrica | M-001 POST_AB_SETTLED | M-002 POST_AB_2 | M-002 POST_AB_2_SETTLED | Δ finales M-002 menos M-001 |
|---|---:|---:|---:|---:|
| RSS Comfy GiB | 2.829 | 2.512 | 2.512 | -0.317 |
| PSS Comfy GiB | 2.813 | 2.499 | 2.499 | -0.314 |
| PSS_Anon GiB | 2.311 | 2.378 | 2.378 | +0.067 (~69 MiB) |
| PSS_File GiB | 0.488 | 0.107 | 0.107 | -0.381 (~390 MiB) |
| VRAM GPU global MiB | 189 | 189 | 189 | 0 |

- `POST_AB_2` marcado por muestra `2026-10-09T05:27:51.853193Z`.
- `POST_AB_2_SETTLED` marcado por muestra `2026-10-09T05:28:51.586367Z`.
- La estabilidad de RSS y PSS_Anon en dos muestras separadas ~60s **no prueba ausencia de variación entre ellas** sin leer la serie completa.
- RSS/PSS totales menores al post M-001 se explican fundamentalmente por un PSS_File inferior. **PSS_Anon residual aumenta 0.067 GiB**; no afirmar "no hay fuga", "RAM completamente reutilizada" ni crecimiento monótono sin una tercera corrida y revisión de la serie.
- El descenso de PSS_File puede deberse a cambios de residencia de páginas file-backed, pero no atribuir causalmente sin `smaps`/ruta de mapeo. Comparar PRE_AB_2 y picos antes de sacar conclusiones.
- El usuario aún no confirmó explícitamente IDs de trabajos/estado terminal en M-002 (sí aportó las marcas POST).

**Siguiente acción única:** obtener `PRE_AB_2`, min/max y actividad por fases de la traza completa M-002 y vincularla a la ejecución A/B antes de decidir M-003 vs D2 ProfilerX. Mantener Context pausado y evitar unload/destrucción.


### M-002 — Análisis íntegro del ZIP, validado (248 muestras)

**Fuente:** adjunto de conversación `M002_memory_AB.zip` con `M002_20261009_052124.jsonl` y `M002_20261009_052124_markers.jsonl`. Detalles íntegros: **[MEMORY_M002_TRACE_ANALYSIS_2026-10-08.md](MEMORY_M002_TRACE_ANALYSIS_2026-10-08.md)**.

- **248 muestras** de 05:21:24.875Z a 05:30:05.934Z; cadencia mediana 2.088s, brecha máxima 2.338s; **PID Comfy 16744** en todas, mismo PID que M-001.
- Marcadores: `PRE_AB_2` 05:21:29.741Z, `POST_AB_2` 05:27:52.938Z, `POST_AB_2_SETTLED` 05:28:52.939Z (las lecturas corresponden a `sample_utc` 0.7–1.4 segundos anteriores).
- **PRE_AB_2:** RSS 2.829090 / PSS_Anon 2.311440 / PSS_File 0.488399 GiB; GPU global 189 MiB.
- **POST_AB_2:** RSS 2.511574 / PSS_Anon 2.377937 / PSS_File 0.107427 GiB; GPU global 189 MiB, idéntico al SETTLED.
- **Máximos muestreados M-002:** RSS 8.686127 GiB @05:26:29.031Z; PSS_Anon 7.214367 GiB @05:26:33.408Z; PSS_File 4.724025 GiB @05:23:58.411Z; GPU global 12125 MiB @05:24:45.510Z.
- Bloques GPU >1000 MiB: 05:22:52–05:23:07 (pico 5373), 05:23:49–05:24:58 (pico 12125), 05:25:25–05:27:04 (pico 12029). **No equivalen automáticamente a número o frontera de jobs**.
- **Reposo post actividad:** 88 muestras de 05:27:06.434Z a 05:30:05.934Z con RSS 2.511574 y PSS_Anon 2.377937 GiB constantes.
- **Comparación finales de M-001 → M-002:** RSS -0.317516 GiB, PSS_Anon +0.066498 GiB (~68 MiB), PSS_File -0.380919 GiB, VRAM global 189→189 MiB. El RSS decreció gracias a menor residencia file-backed; el pequeño aumento de anónima permanece sin propietario identificado.
- **Estado:** dos corridas en mismo PID, M-001 A y B reportados completados; M-002 finalización formal/IDs todavía no recibidos. No se demuestra fuga ni limpieza completa. **Siguiente prueba**: M-003 repetición idéntica en el mismo proceso para contrastar tendencia PSS_Anon, bajo preflight de recursos, antes de instalar ProfilerX.


### M-003 — preflight tercera corrida, aún SIN resultado (2026-10-08 CDMX / 2026-10-09 UTC)
Datos reportados por el usuario, mismo PID previsto 16744 sin reinicio, monitor M-003 activo; marcación `PRE_AB_3` sobre muestra `2026-10-09T05:33:17.087278+00:00`:
- `MemAvailable = 8.67 GiB`; la medición equivalente anterior al M-002 fue 8.78 GiB (~0.11 GiB más). Las cifras de `MemAvailable` son estimaciones Linux con page cache parcialmente recuperable, **no son RSS ni garantía de ausencia de OOM**.
- GPU global usada **189 MiB**, libre reportada **14724 MiB** (NVIDIA T4).
- `RSS = 2.512 GiB`; `PSS = 2.499 GiB`; `PSS_Anon = 2.378 GiB`; `PSS_File = 0.107 GiB`; idéntico al final previo M-002 a la precisión mostrada.
- La RAM total del sistema informada en el preflight anterior es 12.67 GiB. M-002 tuvo un pico de RSS de 8.686 GiB desde 2.512 GiB (aumento 6.174 GiB); comparado con MemAvailable 8.67 GiB indica un **margen aproximado de 2.5 GiB si la corrida es comparable**, pero el cómputo es aproximado y puede ocultar picos simultáneos de otros procesos.
- **Situación:** el usuario indicó que procederá a ejecutar A–B. Aún no hay POST_AB_3, picos ni IDs de M-003. No atribuir éxito, fracaso, acumulación o liberación hasta recibir resultados.

**Siguiente acción:** tras fin de A/B, registrar `POST_AB_3` y `POST_AB_3_SETTLED`; revisar aumento de PSS_Anon respecto a 2.378 GiB y preparar tercera traza, sin limpieza.


### M-003 — cambio de decisión: pausa antes de repetir A→B, auditoría de RAM disponible
**Motivo:** tras el preflight con MemTotal=12.67 GiB, MemAvailable=8.67 GiB, RSS Comfy=2.512 GiB y PSS_Anon=2.378 GiB, el usuario cuestionó expresamente que la RAM disponible fuera tan baja y pidió no continuar con la repetición sin entender la ocupación. El experimento M-003 tiene **marcador PRE_AB_3**, pero **no hay POST_AB_3 ni evidencia de que A/B se haya ejecutado** en esta conversación. No registrar M-003 como completado.

**Corrección del criterio:** la estimación simplificada de margen de ~2.5 GiB (MemAvailable menos variación previa de RSS) no constituye umbral anti-OOM validado; no utilizarla como garantía. MemAvailable de Linux es una estimación de memoria disponible incluyendo caché recuperable y no identifica propietarios. La diferencia total−available es ~4.00 GiB, que incluye tanto procesos como memoria no inmediatamente recuperable. El salto de Comfy PSS_Anon desde M-001 BASELINE 0.719 hasta PRE_AB_3 2.378 GiB es de ~1.659 GiB **cuya función/propiedad no se ha atribuido**, no se puede declarar desperdicio ni necesariamente liberable.

**Siguiente única acción:** captura de solo lectura de `free -h`, campos explicativos de `/proc/meminfo`, `/proc/16744/status` y principales procesos por RSS (sin argumentos potencialmente sensibles). Verificar cgroups del notebook y del proceso Comfy por separado, sin modificar runtime, caches, Torch o CUDA. Luego reevaluar si conviene ProfilerX/atribución CPU o nueva carga. Si la corrida M-003 ya fue arrancada, dejarla terminar sin unload y documentar post antes de más acciones.


### M-003 — diagnóstico de alto consumo mientras/justo después de A→B: momento NO alineado (2026-10-09 UTC)

El usuario informa que la secuencia A–B **ya terminó** y muestra una celda de auditoría de RAM ejecutada alrededor del término del trabajo, pero sin timestamp/orden suficientemente precisos para clasificar la medición como POST_AB_3 estabilizada.

**Valores de la auditoría puntual**:
- MemTotal **12.671 GiB**, MemFree **0.145 GiB**, MemAvailable **3.830 GiB**.
- Cached **3.719 GiB**, Buffers **0.055 GiB**, AnonPages **8.173 GiB**, Mapped **1.773 GiB**, Shmem **0.020 GiB**, Slab **0.303 GiB** (SReclaimable 0.242 GiB).
- `ps -eo pid,ppid,rss,comm --sort=-rss`: proceso ComfyUI PID **16744** RSS **9259768 KiB** (~8.83 GiB); siguiente mayor proceso `node` PID 12086 RSS 388460 KiB; `jupyter-server` PID123 RSS147188 KiB; notebook Python PID800 RSS112116 KiB.
- `/proc/16744/status`: VmRSS 9260152 KiB (~8.83 GiB), RssAnon 7567824 KiB (~7.22 GiB), RssFile 1677988 KiB (~1.60 GiB), RssShmem 14340 KiB (~0.014 GiB), VmSwap 0 KiB; VmSize ~57.6 GiB virtual no equivale a RAM física.
- Las rutas `/proc/self/cgroup` del notebook y `/proc/16744/cgroup` indican ambas `0::/../../jupyter-children`, por lo que la cifra anterior leída en `/sys/fs/cgroup/memory.current` desde el notebook **no representa necesariamente ese cgroup**, y no es apropiada para seguridad.
- A–B **completó según el usuario**, pero el momento de `ps`/`meminfo` relativo al final de B es incierto; los valores de RSS y RssAnon concuerdan aproximadamente con picos muestreados en M-001/M-002. **No inferir retención post-job de 8.83 GiB**.

**Acción inmediata solicitada al usuario:** ejecutar `mark_m003("POST_AB_3")` inmediatamente y `mark_m003("POST_AB_3_SETTLED")` tras 60 s, junto con MemAvailable actual. No ejecutar más workflows, frees, unloads, reinstalaciones ni reinicios hasta recibir los resultados y correlacionar con timestamp.
