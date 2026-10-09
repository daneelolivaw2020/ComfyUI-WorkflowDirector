# M-003 — Tercera corrida A→B: análisis íntegro y decisión de diagnóstico

**Fecha:** 2026-10-08 CDMX / 2026-10-09 UTC.
**Origen:** ZIP `M003_memory_AB.zip` adjunto en conversación, con `M003_20261009_053312.jsonl` (231 muestras) y `M003_20261009_053312_markers.jsonl` (3 marcas). Los archivos originales no se subieron a GitHub; preservar la copia ZIP.

## Entorno y medición
- Misma sesión y **PID Comfy 16744** que M-001 y M-002; no se observa reinicio. ComfyUI 0.39.0; WorkflowDirector 0.0.7-dev; `--cache-none` y `--reserve-vram 0.8`; modo `observe-phase2-nondestructive`. No ProfilerX ni limpieza.
- Traza de **231 muestras** de **05:33:12.982610Z a 05:41:17.340785Z** (~8m04s). Cadencia mediana 2.078 segundos, máxima separación 2.611s, sin huecos >3s. GPU NVML = uso global; RSS/PSS = proceso Comfy según Linux /proc.
- El usuario informó terminada la secuencia A–B y `active_run_id=None` tras ella. **No se obtuvieron IDs de jobs**, ni tiempos formales de fronteras A/B; no asignar segmentos por GPU a un workflow concreto.

## Memoria disponible del sistema (observación posterior)
`/proc/meminfo` después de M-003, suministrado por el usuario:
- MemTotal **12.671 GiB**
- MemFree **4.809 GiB**
- MemAvailable **8.663 GiB**
- Cached **3.880 GiB**
- AnonPages **3.356 GiB**
- WorkflowDirector `active_run_id=None`.

**Interpretación:** la baja de `MemAvailable` durante la fase de ~8.8 GiB RSS era transitoria, y luego el sistema volvió a reportar ~8.66 GiB disponibles. `MemAvailable` incluye páginas cacheadas recuperables estimadas por kernel; no equivale a `MemFree`. La diferencia MemTotal−MemAvailable de ~4.008 GiB **no equivale automáticamente a desperdicio ni a memoria libreable con seguridad**. El RSS de Comfy y la memoria de otras partes del sistema conviven en la cifra del host.

## Marcadores (lecturas exactas de muestras referenciadas en ZIP)

| Métrica | PRE_AB_3 (sample 05:33:17.087278Z) | POST_AB_3 (sample 05:38:42.771752Z) | POST_AB_3_SETTLED (sample 05:39:42.657881Z) |
|---|---:|---:|---:|
| RSS Comfy GiB | 2.511574 | 2.544762 | 2.544762 |
| PSS Comfy GiB | 2.498956 | 2.533617 | 2.533616 |
| PSS_Anon GiB | 2.377937 | 2.414989 | 2.414989 |
| PSS_File GiB | 0.107343 | 0.104952 | 0.104951 |
| PSS_Shmem GiB | 0.013676 | 0.013676 | 0.013676 |
| GPU global MiB | 189 | 189 | 189 |

Respecto a PRE_AB_3, POST_AB_3 aumentó RSS ~0.033188 GiB (~34 MiB), PSS_Anon ~0.037052 GiB (~38 MiB), PSS_File disminuyó ~0.002391 GiB. Marcas más próximas al muestreo, no eventos síncronos al último nodo.

## Máximos de M-003 (no simultáneos)
- **RSS**: 8.865070 GiB a **05:37:03.289807Z**.
- **PSS**: 8.852451 GiB a **05:37:03.289807Z**.
- **PSS_Anon**: 7.240677 GiB a **05:37:30.396139Z**.
- **PSS_File**: 5.213529 GiB a **05:36:41.598920Z**.
- **Private_Dirty**: 7.260979 GiB a **05:37:30.396139Z**.
- **GPU NVML global**: 12125 MiB a **05:35:41.888517Z**.
- Muestras periódicas ~2s: picos sub-intervalo pueden no estar capturados. No sumar máximos ocurridos en instantes distintos.

## Segmentación exploratoria por GPU global >1000 MiB
- Actividad #1: **05:34:42.139346–05:35:54.706086Z**, 35 muestras; pico GPU 12125 MiB; RSS máximo dentro del bloque ~7.784 GiB.
- Actividad #2: **05:36:24.462009–05:38:03.613228Z**, 46 muestras; pico GPU 12029 MiB; RSS máximo del bloque 8.865 GiB y anónimo 7.241 GiB.
- Después de **05:38:05.692961Z**, 94 muestras hasta **05:41:17.340785Z** (~3m12s) en estado aproximadamente estable: RSS **2.544762–2.549629 GiB**, PSS_Anon **2.414989–2.419857 GiB**, GPU global mayoritariamente 189 MiB, con pico aislado 221 MiB. Pequeña variación en ~5 MiB durante los primeros instantes: no afirmar constancia exacta de toda la ventana.
- Umbral GPU arbitrario posterior a la medición, no frontera formal de trabajos.

## Comparación tres corridas en el mismo PID

| Métrica | M-001 | M-002 | M-003 |
|---|---:|---:|---:|
| Muestras | 524 | 248 | 231 |
| RSS pico GiB | 8.898037 | 8.686127 | 8.865070 |
| PSS_Anon pico GiB | 7.137981 | 7.214367 | 7.240677 |
| PSS_File pico GiB | 5.474691 | 4.724025 | 5.213529 |
| VRAM global pico MiB | 12121 | 12125 | 12125 |
| RSS POST GiB | 2.829090 | 2.511574 | 2.544762 |
| PSS_Anon POST GiB | 2.311440 | 2.377937 | 2.414989 |
| PSS_File POST GiB | 0.488348 | 0.107427 | 0.104952 |
| GPU global POST MiB | 189 | 189 | 189 |

- PSS_Anon residual M-001→M-002 **+0.066497 GiB (~68 MiB)**; M-002→M-003 **+0.037052 GiB (~38 MiB)**. Aumentos decrecientes son compatibles con calentamiento/caching/fragmentación o retención acumulativa inicial; **no permiten diagnosticar fuga ni demostrar meseta**.
- Desde BASELINE anterior a M-001 PSS_Anon **0.719 GiB redondeado**, M-003 POST **2.415 GiB**, aumento neto ~1.696 GiB. Esa diferencia **no es automáticamente innecesaria o recuperable**.
- Se produjeron picos anónimos y file-backed, pero PSS_File residual termina ~0.105 GiB. El peak file-backed no es el problema residual principal.

## Decisión / siguiente única acción
**Cerrar D1** para la reproducción funcional de 3 corridas; no cuarta carga ciega. El paso siguiente es **atribuir el residuo CPU anónimo** mediante lectura pasiva en el mismo proceso: inspeccionar descomposición de `/proc/16744/smaps` por anon/[heap]/file, `smaps_rollup` y directorio de cgroup real del PID; mantener el proceso y registro de Comfy sin cambios. Esto no identifica objetos Python/Torch, pero discrimina [heap] vs asignaciones anónimas y mmap file-backed.
Después usar ProfilerX pinned aislado, con nuevo baseline y reinicio sólo Comfy según runbook, para cruzar deltas por nodo; no lo confundir con atribución directa de referencias vivas. Más adelante inventario interno read-only de registro de modelos/Torch allocadores si sigue la duda.
No llamar `/free`, `empty_cache`, `unload_all_models` ni reinstalar Torch/CUDA; Context PR #6 sigue pausado.
