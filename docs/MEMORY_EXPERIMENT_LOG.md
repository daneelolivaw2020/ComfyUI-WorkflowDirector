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


### M-003 — POST_AB_3 y POST_AB_3_SETTLED: tercera repetición completada (2026-10-09 UTC)
El usuario informó que la secuencia A–B ya había finalizado; posteriormente ejecutó la celda de marcas posjob, sin realizar cleanup. **El valor alto de RSS ~8.83 GiB de la auditoría previa fue transitorio**, pues cayó a ~2.545 GiB al marcar POST_AB_3. Correlación con la frontera de job exacta aún pendiente (no IDs).

**Datos suministrados directamente de Colab:**
- `POST_AB_3` muestra `2026-10-09T05:38:42.771752Z`: RSS **2.545 GiB**, PSS **2.534 GiB**, PSS_Anon **2.415 GiB**, PSS_File **0.105 GiB**, GPU global **189 MiB**.
- `POST_AB_3_SETTLED` muestra `2026-10-09T05:39:42.657881Z`, tras ~60s: **idénticos valores redondeados**; PID 16744 aún vivo.
- El script imprimió etiquetas `RAM disponible:` pero **no muestra ningún valor** de `MemAvailable` en la respuesta; por tanto, el dato de RAM disponible posterior a M-003 es desconocido y hay que recuperarlo. Antes de la ejecución el sistema reportó 8.67 GiB disponibles y durante un pico la auditoría reportó 3.830 GiB; no inferir cuánto quedó al concluir.

**Comparación de posjobs consecutivos (GiB):**
| Métrica | M-001 | M-002 | M-003 |
|---|---:|---:|---:|
| RSS | 2.829 | 2.512 | 2.545 |
| PSS | 2.813 | 2.499 | 2.534 |
| PSS_Anon | 2.311 | 2.378 | 2.415 |
| PSS_File | 0.488 | 0.107 | 0.105 |
| GPU global MiB | 189 | 189 | 189 |

El incremento residual anónimo es ~0.067 GiB de M-001 a M-002 y ~0.037 GiB de M-002 a M-003 (aprox. 69 y 38 MiB respectivamente), total ~106 MiB en dos transiciones. Respecto de la BASELINE pre-M-001, PSS_Anon sube desde 0.719 a 2.415 GiB (+1.696 GiB). La caída observada de RSS del pico de ~8.83 GiB a 2.545 GiB **no demuestra** que el resto sea recuperable ni prueba ausencia de retención indebida.

**Decisión:** no lanzar cuarta repetición ni intentar unload ciego por ahora. Primero medir `MemAvailable` posterior a M-003 con una lectura directa de /proc y capturar comparadores del proceso/cachés del sistema, luego estudiar la atribución de memoria anónima del proceso. ProfilerX puede ayudar a atribuir deltas por nodo pero no establece por sí solo propietarios de memoria CPU residual ni una fuga. No tocar Context PR#6.


### M-003 — ZIP completo recibido, D1 cerrada con tres corridas comparables

Archivo original adjunto en la conversación: `M003_memory_AB.zip`; análisis reproducible y completo en **[MEMORY_M003_TRACE_ANALYSIS_2026-10-08.md](MEMORY_M003_TRACE_ANALYSIS_2026-10-08.md)**. El ZIP contiene 231 muestras / 3 marcadores, 05:33:12.983–05:41:17.341Z, cadencia mediana ~2.078 s y sin huecos >3 s; PID Comfy 16744 idéntico en las tres sesiones.

**M-003 máximos:** RSS 8.865070 GiB @05:37:03Z, PSS_Anon 7.240677 GiB @05:37:30Z, PSS_File 5.213529 GiB @05:36:41Z, VRAM GPU global 12125 MiB @05:35:41Z. **POST_AB_3:** RSS 2.544762, PSS 2.533617, PSS_Anon 2.414989, PSS_File 0.104952 GiB; NVML global 189 MiB. 94 muestras a partir de 05:38:05Z (~3m12 s de reposo) sin acumulación relevante adicional (~5 MiB de rango inicial en RSS/anon).

**Medición global *después* de ejecutar:** MemTotal 12.671 GiB, MemFree 4.809 GiB, MemAvailable **8.663 GiB**, Cached 3.880 GiB, AnonPages 3.356 GiB; Director active_run_id=None. **Esto demuestra que el MemAvailable bajo (3.830 GiB) observado cerca del pico no es el estado de reposo final.** No confundir 4.008 GiB (MemTotal−MemAvailable) con memoria inútil o descargable.

Tres finales PSS_Anon: **2.311440 → 2.377937 → 2.414989 GiB**; +68 MiB y luego +38 MiB (~+106 MiB total). No hay evidencia de incremento grande sin límite en estas tres corridas, pero tampoco está demostrada la meseta o el propietario de los ~1.696 GiB adicionales desde el BASELINE 0.719 GiB original.

**Decisión:** cerrar pruebas de reproducción D1, no repetir A–B sin un fin discriminativo. **Siguiente paso único:** observar `/proc/16744/smaps` y estado/cgroup del proceso ya inactivo para atribuir resident anonymous a tipos de mapeo ([heap], anon, file COW) sin hooks ni CUDA y sin descargar nada. Más adelante instalar ProfilerX pinned como experimento D2 independiente si hace falta atribución por nodo. Sin IDs nativos A/B aún no se pueden asignar exactamente los bloques GPU.


### M-004 — Mapa pasivo de regiones del PID Comfy post-M-003 (2026-10-08 CDMX)

**Fuente:** salida aportada por el usuario de inspección `/proc/16744/smaps` en reposo. Sin intervención sobre el runtime; **3125 regiones inspeccionadas**.

| Clasificación de mapeo (script) | RSS GiB | PSS GiB | Anonymous GiB | Private_Dirty GiB |
|---|---:|---:|---:|---:|
| ANON / MMAP | 2.087 | 2.087 | 2.087 | 2.087 |
| HEAP (`[heap]`) | 0.271 | 0.271 | 0.271 | 0.271 |
| FILE MAPPING / COW | 0.186 | 0.175 | 0.056 | 0.076 |
| STACK / OTHER | ~0.000 | ~0.000 | ~0.000 | ~0.000 |

**Comprobación:** anonymous total ~2.414 GiB ≈ PSS_Anon post-M-003 2.415 GiB (diferencia de redondeo). RSS suma ~2.544 GiB ≈ RSS post-M-003 2.545 GiB. La mayor fracción de RAM anónima está en **regiones privadas sin ruta de archivo (2.087 GiB)**, no en el `[heap]` principal (~0.271 GiB).

**Mayores regiones por memoria anónima reportadas:** `[heap]` ~266 MiB, otras `ANON/MMAP` ~83.0, ~81.9, ~80.3 MiB y múltiples regiones `ANON/MMAP` de ~63.0 MiB residentes. Son **regiones**, no objetos ni necesariamente una asignación por región. Las regiones ~63 MiB podrían ser compatibles con heaps secundarios de arena `malloc`/glibc en aplicaciones con múltiples hilos; **HIPÓTESIS NO DEMOSTRADA**. También son posibles otras estrategias allocator y tensores CPU fuera del `[heap]`.

**Relevancia:** atribución VMA ≠ identidad del allocator ni prueba de objeto vivo. No afirmar que los 2.087 GiB sean "fuga" o que se puedan devolver sin riesgo. Comparación con baseline ANTES de M-001 a nivel VMA **no disponible**; no atribuir todo este subtotal al incremento +1.696 GiB desde baseline.

**Siguiente acción única:** inspección más precisa *read-only* de tamaños virtuales, RSS anónima, permisos, vecinos y `VmFlags` de las regiones ~63 MiB, agrupar número y suma RSS. No ejecutar `malloc_trim`, `MALLOC_ARENA_MAX`, `MALLOC_MMAP_THRESHOLD_`, /free ni unload mientras no haya evidencia y una corrida de validación aislada. ProfilerX posterior puede atribuir nodo de crecimiento pero no necesariamente la propiedad CPU final.


### M-005 — Patrones anónimos de 64 MiB, indicios de heaps secundarios glibc (2026-10-08 CDMX)

**Salida del usuario, sobre el mismo PID Comfy 16744 en reposo, /proc/16744/smaps:**
- **540** regiones anónimas por el clasificador; **2.087 GiB** de memoria anónima residente.
- **13** regiones con `Anonymous` entre **60 y 66 MiB**, suma **818 MiB** (cuantizadas por la salida). Entre las 15 regiones mayores están tres mapeos de ~83.0, 81.9, 80.3 MiB y muchas `rw-p` de ~63.0 MiB.
- La inspección de vecinos muestra sistemáticamente bloque `rw-p` de **63 MiB** junto a bloque sin acceso `---p` de **1 MiB** (para 5 ejemplos). Total virtual aparentemente **64 MiB** por pareja. `VmFlags` de las regiones grandes: `rd wr mr mw me ac sd`.
- El proceso reporta **36 hilos**.

**Interpretación y fuente técnica verificada:** glibc `malloc/arena.c` documenta heaps secundarios asignados mediante `mmap`, alineados al límite `HEAP_MAX_SIZE` (usualmente 64 MiB en glibc 64-bit común), reservando PROT_NONE y habilitando parcialmente con mprotect. Documentación upstream https://codebrowser.dev/glibc/glibc/malloc/arena.c.html; explicación de trade-offs entre arenas y memoria: https://www.man7.org/linux/man-pages/man3/mallopt.3.html.
El patrón 63MiB rw +1MiB ---p es **MUY compatible con heaps secundarios de malloc arenas**, reforzado por multihilo, pero aún **no confirmado**: falta verificar direcciones alineadas a 64MiB, adyacencia exacta y nombres `[anon: glibc: malloc arena]` si disponibles. **13 heap mappings ≠ automáticamente 13 arenas.**
Los **818 MiB están residentes, no constituyen una medición de bytes libres dentro del allocator**, ni garantiza que sean liberables. El mapa completo incluye 2.087 GiB anon mmap, 0.271 GiB [heap] y 0.056 GiB anónimo COW-file, pero no sabemos cuáles regiones aportaron el crecimiento +1.696 GiB vs baseline anterior.

**Siguiente paso (sin modificar proceso):** verificar `start_addr mod 64MiB`, adyacencia `rw-p/---p`, tamaño combinado 64MiB y etiquetas reales de VMA en `/proc/16744/smaps`; registrar número de bloques y RSS. No tocar `malloc_trim`, `MALLOC_ARENA_MAX`, `MALLOC_MMAP_THRESHOLD_` ni procesos CUDA. Después decidir si vale la pena una instrumentación `malloc_info` acotada en entorno aislado o si los datos de node attribution de ProfilerX son prioritarios.


### M-006 — Confirmación geométrica fuerte de heaps secundarios glibc (2026-10-08 CDMX)

**Salida literal del usuario (PID Comfy 16744, 13 candidatos de smaps, solo lectura):**
- **13/13** regiones anónimas `rw-p` candidatas de ~62.8–63.1 MiB tienen `start_addr % (64 MiB) == 0`.
- **13/13** tienen región `---p` adyacente que completa una pareja virtual **exacta de 64 MiB** (el script indica `guard=antes,despues` para varios porque bloques contiguos pueden ser vecinos por ambos lados). `---p` es reserva inaccesible; llamarla *guard page* de seguridad es incorrecto sin comprobar intención; es principalmente espacio reservado.
- **818 MiB** anónimos residentes dentro de los 13 bloques candidatos, de los **2.087 GiB** anónimos residentes en regiones mmap sin nombre; a diferencia de baseline, no sabemos qué parte corresponde a datos vivos.
- Ejemplos de direcciones virtuales alineadas: `0x795820000000`, `0x795828000000`, `0x79582c000000`, etc.; no registrar más datos personales.
- El proceso informó previamente **36 hilos**. `getconf GNU_LIBC_VERSION` se invocó, pero la salida entregada mostró el objeto `CompletedProcess` sin cadena real de versión; la versión glibc exacta **sigue sin documentarse**.

**Interpretación:** geometría sumamente característica de heaps secundarios de `ptmalloc`/glibc. Su implementación en `malloc/arena.c` reserva regiones `mmap` alineadas a `HEAP_MAX_SIZE` y habilita páginas `mprotect`: [código fuente glibc](https://codebrowser.dev/glibc/glibc/malloc/arena.c.html), con HEAP_MAX_SIZE usual 64MiB en glibc 64-bit. **Muy alta confianza en la clase de mapeo, no en el número de arenas** (un arena puede poseer múltiples heaps) y **ninguna medición de bytes libres dentro del asignador**. Las 13 regiones suman RSS, no "818 MiB liberables"; los rangos >63 MiB o parciales pueden pertenecer a otros allocators/mmap.

**Próxima decisión técnica:** no repetir inspección de alineaciones ni ejecutar `malloc_trim()`. La forma informativa de medir ocupación libre por arenas es `malloc_info(0, FILE*)`, que exporta XML del estado del asignador desde **el mismo proceso** ([manual Linux](https://man7.org/linux/man-pages/man3/malloc_info.3.html)); ejecutarlo desde el kernel del notebook mediría otro PID y no serviría. Requiere diseñar un punto de consulta read-only en Comfy mediante instrumentación aislada/controlada y reinicio solo de Comfy, o un método apropiado equivalente que no modifique en caliente el proceso actual. `malloc_info` informa arenas/fragmentos, **no garantiza bytes liberables físicamente**; los resultados deberían correlacionarse con RSS/PSS. No adjuntar debugger en vivo ni inyectar código y no instalar profilers hasta definir el procedimiento con rollback.


### M-007 — Prototipo de `malloc_info` agregado a PR #7, todavía sin instalar (2026-10-08 CDMX)

Implementado exclusivamente en `feature/memory-diagnostics`:
- `workflowdirector/allocator_diagnostics.py`: estadísticas glibc `malloc_info` agregadas desde el mismo PID con ctypes, sin `torch`, con lectura XML acotada y sin llamadas a descarga/trim.
- `workflowdirector/routes.py`: endpoint opt-in `GET /workflowdirector/memory/glibc`, sólo registrado cuando `WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS=1` al arranque; consulta local con guardas cola nativa Comfy (running y pending) y Director, verificaciones antes/después, 409 si busy. No es una garantía de exclusión atómica frente a nuevos trabajos y exige desactivar Auto Queue.
- `tests/test_allocator_diagnostics.py`: parseo del XML sin doble conteo y smoke C ABI **en subproceso desechable**, opt-in/desactivación y verificación de ausencia de operaciones destructivas.
- Diseño/puertas: [MEMORY_GLIBC_ALLOCATOR_INSPECTION_DESIGN.md](MEMORY_GLIBC_ALLOCATOR_INSPECTION_DESIGN.md).
- Inicialmente CI falló por un falso positivo de prueba textual (`import torch` en un docstring negativo); corregido inspeccionando AST real, sin cambiar lógica del colector.
- **CI exitosa**: commit `5acde78b92343a4e29a8ad9f142b2526d182098b`, [Core tests run 37891129776](https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector/actions/runs/37891129776), matrices Python 3.11 y 3.13 (ambas success). Esto prueba los tests en runners, **no prueba ejecución en el Comfy de Colab**.
- **Próxima única acción:** clonar ese commit a carpeta de inspección separada en Colab y ejecutar un smoke `capture_allocator()` en un *subproceso Python desechable* para validar la ABI/libc del Colab sin entrar al PID Comfy; luego verificar ruta real/versión del custom node y planificar reinicio sólo de Comfy con los mismos flags, opt-in en entorno, siempre con rollback. No ejecutar A–B todavía, ni alterar instalación validada ni `--cache-none`.


### M-007 — Smoke glibc en subproceso aislado de Colab, APROBADO (2026-10-09 UTC)
Salida aportada por el usuario de prueba del colector desde checkout separado `/content/WorkflowDirector-Glibc-Probe`:
- **Commit del checkout**: `d61770d6d7c1eeaf8761a022a7c96c465abfa53d` (`feature/memory-diagnostics`, posterior a los tests CI verdes).
- `subprocess.run([sys.executable, "-c", ...], cwd=TEST_DIR, timeout=20)` ejecutó `capture_allocator()` **en un proceso separado**, no en ComfyUI.
- **Código de salida: 0**; PID prueba `39290`; `glibc_version="2.39"`; `heap_entries=1`; `arena_system_current_bytes=2416640`; `free_list_estimate_bytes=227400`.
- Salida `PRUEBA AISLADA CORRECTA`. Confirma llamada nativa y parseo básico del XML en Colab (glibc 2.39). **No prueba** seguridad sobre ComfyUI en vivo ni permite atribuir sus ~818 MiB de heaps alineados.
- **No modificación de ComfyUI** a partir de esta prueba; sin cambios Torch/CUDA/Context ni llamadas unload/trim.
- **Próxima acción única**: inspeccionar read-only estado git y ruta del **custom node activo** y mecanismo de arranque/entorno Comfy antes de preparar actualización controlada y reinicio de **sólo el proceso Comfy**. Preservar rama validada y argumentos reales `--cache-none`, `--reserve-vram 0.8`, rutas Drive, etc.; comprobar ausencia de cambios locales antes de desplegar.


### M-008 — pre-deployment verification, ComfyUI remains unchanged (2026-10-08 CDMX)
- Comfy actual reportado PID **16744**, comando `/usr/bin/python3 /content/ComfyUI/main.py --listen 127.0.0.1 --port 8188 --output-directory /content/drive/MyDrive/AI/output/26-10-08 --reserve-vram 0.8 --verbose INFO --dont-print-server --preview-method taesd --enable-cors-header '*' --user-directory /content/ComfyUI/user --enable-manager-legacy-ui --cache-none`.
- Custom node path `/content/ComfyUI/custom_nodes/ComfyUI-WorkflowDirector`, commit `62d43b1ddb169deba69135d5c7ebbd420d1ba5e0`, detached HEAD, `git status --porcelain` vacío; health ready true, active_run_id null, modo `observe-phase2-nondestructive`.
- Comparación GitHub commit base contra HEAD rama `feature/memory-diagnostics`: **ahead 36/behind 0**, único código runtime cambiado `workflowdirector/routes.py` (59 líneas añadidas) y nuevo `workflowdirector/allocator_diagnostics.py`; el resto documentación, watcher y tests.
- CI para código del colector en `5acde78b92343a4e29a8ad9f142b2526d182098b` **success** en Py 3.11 y 3.13. Prueba aislada Colab glibc 2.39 aprobada, PID prueba 39290. **No hay todavía prueba de ruta glibc dentro del proceso ComfyUI**.
- **Siguiente:** despliegue controlado reversible de solamente `routes.py` + `allocator_diagnostics.py`, haciendo copia `routes.py` y preservando argv y env del proceso vivo; reiniciar **solo ComfyUI**, habilitar `WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS=1`, consultar solo cuando cola nativa vacía, guardar salida, revertir en caso de fallo. No tocar `--cache-none`, modelos, Context, CUDA o PyTorch. Si el proceso no termina limpiamente, NO enviar SIGKILL a ciegas.


### M-008 — despliegue de dos archivos preparado; Comfy aún sin reiniciar

Confirmado por el usuario después de ejecutar la celda de preparación: `PREPARACION COMPLETADA`. Respaldo `/content/WD_GLIBC_BACKUP_20261009_060742` del `workflowdirector/routes.py` original; copia de `routes.py` y `allocator_diagnostics.py` desde checkout `/content/WorkflowDirector-Glibc-Probe` en commit `d61770d6d7c1eeaf8761a022a7c96c465abfa53d`. Plugin runtime `/content/ComfyUI/custom_nodes/ComfyUI-WorkflowDirector` sigue en commit `62d43b1ddb169deba69135d5c7ebbd420d1ba5e0` con cambios locales esperados exactamente: `M workflowdirector/routes.py` y `?? workflowdirector/allocator_diagnostics.py`.

**Aún sin reinicio:** proceso original Comfy PID 16744 ejecutando código cargado anterior. Próximo paso: reiniciar solo proceso Comfy, preservando argv completo, cwd y entorno de /proc, añadiendo `WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS=1`; desactivar Auto Queue y verificar cola nativa vacía; arrancar e interrogar solo por loopback `GET /workflowdirector/memory/glibc`. Si falla, revertir rutas y reiniciar código original sin flag, sin SIGKILL forzado, sin reinstalar ni modificar memoria CUDA. No registrar éxito hasta recibir salida de reinicio.

### M-009 — Cambio de runtime Colab: se inicia NUEVA cohorte, baseline antes de primer job (2026-10-09 CDMX)

El usuario informa que agotó las horas de Colab Free y está creando una **nueva sesión de runtime**, reinstalando desde sus celdas. Por tanto:
- El PID anterior **16744** ya no debe utilizarse; se debe descubrir dinámicamente el PID nuevo desde `/proc`, y verificar el puerto real/argv `--cache-none`.
- La preparación del anterior runtime en `/content/ComfyUI/custom_nodes/ComfyUI-WorkflowDirector` y el respaldo `/content/WD_GLIBC_BACKUP_20261009_060742` eran **efímeros**. La ruta de diagnóstico opt-in no fue probada en ComfyUI: su prueba satisfactoria fue únicamente en un subproceso aislado Colab, glibc 2.39 (la nueva sesión puede diferir).
- Los ZIP M-001, M-002, M-003 y análisis en GitHub siguen válidos como registro histórico del runtime previo, **no un mismo PID o una repetición longitudinal**.
- Los workflows A/B no están guardados explícitamente; recreaciones distintas no son comparables estrictamente con M001–3. Posibilidad de recuperación desde metadatos ComfyUI de PNGs conservados en Drive (si efectivamente son PNGs con workflow embebido); no suponer que existen ni regenerar de memoria a ciegas.
- **Nueva prioridad:** capturar baseline frío del nuevo runtime ANTES de todo job, idealmente a) RAM sistema antes de iniciar Comfy; b) al finalizar imports y arranque de Comfy pero antes de la primera cola, c) posterior a instrumentación glibc en segundo arranque, registrando el cambio de PID/baseline. Incluye MemAvailable, MemFree, Cached, AnonPages, proceso Comfy RSS/PSS/PSS_Anon/PSS_File y GPU global; versión Py/Torch sin importar torch en notebook, argv/caché, health y cola nativa. Etiquetar nueva cohorte distinta de M001-M003. **No repetir todas las celdas de tests antiguas** ni ejecutar setup que borre la instalación una vez funcional.
- No introducir simultáneamente ProfilerX u otros custom nodes; mantener `feature/universal-context-nodes` pausada. Reinstalar diagnóstico como experimento separado y reversible sólo después del baseline original y verificación de compatibilidad.


### M-009 — instalación nueva completada, justo antes del primer arranque de Comfy
El usuario confirma que la nueva sesión de Colab pertenece a **otra cuenta**, por lo que ninguna ruta efímera previa (`/content/WD_GLIBC_BACKUP_20261009_060742`, copia de prueba/archivos locales previos) debe darse por existente. **Terminó todas las celdas de instalación y se detuvo ANTES de arrancar ComfyUI por primera vez.**

**Decisión:** capturar `M009_PRE_COMFY` (MemTotal, MemAvailable, MemFree, Cached, AnonPages, Shmem, SReclaimable, GPU NVML global, Python/Torch metadata sin import torch, glibc version, Comfy/WorkflowDirector Git SHAs y estado, ausencia de PID Comfy). **No ejecutar ninguna celda que reinstale / borre ComfyUI**, ni arranque ni workflow antes de esta lectura. Después preparar el opt-in del colector glibc ANTES del primer arranque con backup de los dos archivos en el runtime nuevo y plan exacto de argv/flags; evitar reinicio extra. Tratar como cohorte independiente M009, no usar valores o PID 16744 de la sesión anterior.


### M-009 — nueva cuenta Colab, PRE_COMFY baseline confirmado (2026-10-09T06:22:42.256795Z)

**El usuario ejecutó `M009_PRE_COMFY` y el reporte confirma CERO PID Comfy activos**, tras la instalación completa y antes de iniciarlo por primera vez. Registro original en el runtime nuevo `/content/M009_PRE_COMFY.json` (efímero).
- Python **3.13.15**; PyTorch instalado (leído metadata, sin importar): **2.11.0+cu130**; glibc **2.39**.
- GPU NVML global **Tesla T4, 0 MiB utilizados / 15360 MiB totales**.
- MemTotal **12.6714 GiB**; MemFree **0.2593 GiB**; MemAvailable **11.2450 GiB**; Cached **10.5967 GiB**; AnonPages **0.8512 GiB**; Shmem **0.0050 GiB**; SReclaimable **0.5474 GiB**.
- `/content/ComfyUI/main.py` existe. Comfy git **b0b743566f65daafc423b4fea8a2fbda94b3384a** (el tag/version de Comfy se verificará tras el primer arranque).
- Plugin instalado `/content/ComfyUI/custom_nodes/ComfyUI-WorkflowDirector`, git **62d43b1ddb169deba69135d5c7ebbd420d1ba5e0** y **sin cambios locales**. `workflowdirector/allocator_diagnostics.py` aún **no instalado**.
- CUIDADO: MemFree=0.2593GiB no es una alarma por sí solo porque Cached=10.5967GiB y MemAvailable=11.245GiB; Linux puede recuperar páginas de caché. Estas cifras son globales del sistema, no PSS de Comfy (aún no ejecutado).

**Siguiente:** instalar *antes del primer arranque* sólo dos ficheros del commit de código ya validado `5acde78b92343a4e29a8ad9f142b2526d182098b` (`workflowdirector/routes.py` sha1 blob `e16a6f49e9e0e1adbab3e1c8677e502268207c8c`; `workflowdirector/allocator_diagnostics.py` blob `ebc806b4989ba956d7b0f369943ea68e432cbefa`), previa copia de seguridad y revisión de proceso ausente. Activar el opt-in `WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS=1` en el entorno del proceso de arranque. Nunca ejecutar celdas de instalación que borren Comfy después. La instalación no se considera realizada hasta que el usuario confirme salida.


### M-009 — glibc diagnóstico preparado en nueva cuenta ANTES del primer arranque (2026-10-09 UTC)
Salida del usuario:
- `M-009 DIAGNOSTICO PREPARADO` — backup original `/content/WD_M009_BACKUP_20261009_062506`; exactamente dos archivos instalados/verificados por blobs: `M workflowdirector/routes.py`, `?? workflowdirector/allocator_diagnostics.py`.
- `WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS=1` presente en `os.environ` del notebook; **todavía no se ha iniciado ComfyUI**, por tanto opt-in efectivo en el proceso y endpoint sin verificar. Git base sigue en `62d43b1...` con modificaciones esperadas.
- Próxima acción: utilizar **la celda de arranque habitual del usuario** sin alterar su ruta de salida, Comfy flags, modelo, Python, Torch/CUDA o módulos; asegurar que el proceso hijo herede la env `WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS=1`, incluso si la celda fabrica explícitamente otro `env`. Después, **antes de ningún workflow**, comprobar health, `/queue`, endpoint `/workflowdirector/memory/glibc`, proceso/PID, y `/proc/<pid>/smaps_rollup`, `/proc/meminfo`. Guardar `M009_COMFY_COLD.json` y comparar con `M009_PRE_COMFY.json` sin mezclar ambientes.


### M-009 — COLD COMFY baseline con malloc_info en el PID Comfy, ANTES de cualquier workflow (2026-10-09 UTC)

**Primer éxito de la nueva ruta glibc en el proceso Comfy activo.** El usuario ejecutó el plugin con instrumentación preparada y `WORKFLOWDIRECTOR_GLIBC_DIAGNOSTICS=1`. Archivo local del nuevo runtime: `/content/M009_COMFY_COLD.json` (no disponible remotamente), mostrado mediante salida en conversación.

- PID Comfy **6177**; puerto **8188**, ComfyUI **0.39.0**, `--cache-none=True`, `active_run_id=None`, cola nativa vacía, opt-in visible dentro del proceso.
- Proceso en reposo **antes de cualquier workflow**: RSS **1.2874 GiB**, PSS **1.2708 GiB**, PSS_Anon **0.7447 GiB**, PSS_File **0.5163 GiB**.
- Sistema en arranque de Comfy: MemFree **0.2565 GiB**, MemAvailable **10.3184 GiB**, Cached **9.5490 GiB**, AnonPages **1.6775 GiB**. Comparación PRE_COMFY: MemAvailable 11.245 GiB, Cached 10.5967 GiB, AnonPages 0.8512 GiB. La baja de MemAvailable ~0.927 GiB mientras Comfy arranca es compatible con el coste del proceso, pero NO se puede atribuir exclusivamente por diferencias de estadísticas globales.
- **glibc 2.39 nativa en ese PID**: **16** entradas `<heap>` de arenas; espacio actual sistema de arenas `arena_system_current_bytes = 300.61 MiB`, **`free_list_estimate_bytes = 16.28 MiB`** (total fast+rest del XML), `direct_mmap_bytes = 15.18 MiB`. No equivalen a RAM residente ni "bytes liberables"; `malloc_info` no incluye todas las cachés tcache y asignaciones nativas de otras bibliotecas.
- Comparación histórica pre-M001 del antiguo runtime: RSS ~1.256668 GiB y PSS_Anon ~0.719337 GiB; nuevo baseline **no idéntico** pero similar (RSS ~+0.031 GiB, anon ~+0.025 GiB). No confundir PID 6177 con 16744 ni interpretar como cadena longitudinal.
- **Siguiente único experimento:** captura de mem RSS/PSS y `malloc_info` inmediatamente DESPUÉS del primer workflow pesado reproducible en el mismo PID, y asentado +60 s. Si A/B original no disponible, recuperar workflow del PNG Comfy en Drive cuando exista o crear y **guardar** un workflow pesado A con sus parámetros registrados; no hace falta que sea idéntico para comparar *dentro* de M009, pero no contrastar picos entre cohortes como si fueran idénticos. No instalar ProfilerX ni intentar `malloc_trim`/unload ni ejecutar diagnosis cuando cola activa. Precaución: `malloc_info` corresponde a los contadores free-list, no garantiza memoria que el SO pueda liberar.
