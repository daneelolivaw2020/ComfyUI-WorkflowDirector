# M-001 — Análisis de la traza externa A→B (Colab Free T4)

**Fecha de adquisición:** 2026-10-08 CDMX / 2026-10-09 UTC.
**Estado:** D1 completó una corrida real de la secuencia A→B, ambas ejecuciones reportadas por el usuario como correctas. **Análisis descriptivo, no diagnóstico de fuga.**
**Fuente original:** ZIP `M001_memory_AB.zip` compartido en la conversación; contiene `memory_20261009_045123.jsonl` y `memory_20261009_045123_markers.jsonl`. El ZIP está en la conversación, **no se ha subido al repositorio**. Este documento conserva todos los resultados derivados necesarios si Colab se desconecta.

## Entorno / instrumento
- ComfyUI PID 16744, versión API 0.39.0; WorkflowDirector 0.0.7-dev, `observe-phase2-nondestructive`; `--cache-none`, `--reserve-vram 0.8`; director.io `/content/ComfyUI`.
- Python 3.13.15, Torch instalado 2.11.0+cu130; Tesla T4 (15360 MiB), driver 580.82.07; proceso GPU reportado por `nvidia-smi` como **uso global**.
- Observador externo `scripts/memory_watch.py` proveniente de revisión `4917217d31ffa4c06154adc7d0c771fe41ce11ee`, **sin torch ni cleanup**.
- 524 muestras, entre **2026-10-09T04:51:23.648159Z** y **2026-10-09T05:09:26.541789Z** (~18m03s). Intervalo median ~2.056s, máximo ~2.533s, ninguna separación >3s. PID idéntico en todas las muestras. GPU global disponible en las 524; `Swap` del proceso fue 0 en las muestras.
- Se registraron tres marcas: BASELINE 04:57:58.835Z (muestra 04:57:57.974Z), POST_AB 05:05:22.108Z (muestra 05:05:20.788Z), POST_AB_SETTLED 05:05:37.109Z (muestra 05:05:35.244Z).
- **Faltan:** marca PRE_AB y registros con `prompt_id`, `run_id`, estado y timestamps para asignar definitivamente la primera/segunda actividad a A/B. No afirmar que cada ventana equivale exactamente a un workflow.

## Lecturas exactas en marcas

| Métrica | BASELINE | POST_AB | POST_AB_SETTLED | Diferencia final |
|---|---:|---:|---:|---:|
| RSS GiB, Comfy | 1.257 | 2.829 | 2.829 | +1.572 |
| PSS GiB, Comfy | 1.241 | 2.813 | 2.813 | +1.572 |
| PSS_Anon GiB | 0.719 | 2.311 | 2.311 | +1.592 |
| PSS_File GiB | 0.512 | 0.488 | 0.488 | -0.024 |
| PSS_Shmem GiB | 0.010 | 0.014 | 0.014 | +0.004 |
| VRAM GPU global MiB | 105 | 189 | 189 | +84 |

Todas estas magnitudes reflejan las muestras más recientes disponibles al tomar el marcador, no lecturas exactamente simultáneas al evento.

## Máximos medidos en toda la traza (NO coocurren)

| Métrica | Máximo | Timestamp UTC |
|---|---:|---|
| RSS Comfy | 8.898 GiB | 05:03:28.474544 |
| PSS Comfy | 8.882 GiB | 05:03:28.474544 |
| PSS_Anon | 7.138 GiB | 05:03:59.415631 |
| PSS_File | 5.475 GiB | 05:02:51.272411 |
| `Private_Dirty` | 7.158 GiB | 05:03:59.415631 |
| VRAM global | 12121 MiB | 05:01:53.466667 |

Los máximos son de muestras de ~2s; pueden existir picos más cortos no capturados. No sumar máximos de distintos instantes. `PSS_File` alto durante la ejecución **es compatible con mmap/páginas de modelos**, pero no demuestra el fichero ni el propietario; se requeriría `/proc/PID/smaps` o perfiles dirigidos.

## Segmentación exploratoria por actividad GPU (>1000 MiB global)
**Umbral descriptivo elegido después de ver la traza; no es un evento del WorkflowDirector.**

1. **Actividad GPU #1:** 05:00:50–05:02:04Z, 36 muestras por encima de umbral, pico GPU 12121 MiB. La RSS alcanzó aproximadamente 7.30 GiB en el periodo amplio 05:00:24–05:02:04.
2. **Valle de GPU:** 05:02:06–05:02:18Z, GPU 189 MiB mientras RSS comenzó en ~2.810 GiB y subió hasta ~3.58 GiB al comenzar la fase siguiente, incluyendo preparación CPU. En 05:02:06 PSS_Anon ~2.276 GiB y PSS_File ~0.505 GiB. La subida durante el valle **impide llamarlo barrera POST_A precisa** sin IDs.
3. **Actividad GPU #2:** 05:02:31–05:04:08Z, 45 muestras por encima de umbral, pico GPU 12029 MiB, RSS max ~8.898 GiB. `PSS_File` temporal 5.475 GiB alrededor de 05:02:51Z y `PSS_Anon` máximo 7.138 GiB alrededor de 05:03:59Z.
4. **Reposo post-ejecución:** desde 05:04:10.490Z hasta 05:09:26.542Z (~5m16s). RSS ~2.8291 GiB, PSS_Anon ~2.3114 GiB y GPU global 189 MiB, **prácticamente constantes en ~154 muestras**; ninguna caída espontánea posterior visible.

## Conclusiones verificadas y NO verificadas

1. La secuencia A/B terminó correctamente según el usuario, en el mismo PID, y la instrumentación no muestra una falla de proceso. Se observaron dos bloques de alta actividad GPU pero la asignación por ID aún es pendiente.
2. La memoria de archivo **creció mucho durante los trabajos** y cayó casi a la línea base al acabar; por tanto, no explica el +1.57 GiB de RSS residual de esta corrida.
3. El residuo final se concentra en **PSS_Anon +1.592 GiB**, persistente al menos 5m16s de reposo. Esto **no prueba fuga**, imposibilidad de liberar memoria ni que objetos de modelo sigan vivos.
4. Entre las dos actividades GPU, RSS llegó brevemente a ~2.81 GiB, comparable al post final de ~2.83 GiB. **No hay evidencia de aumento monotónico del residuo tras la segunda actividad**. Para demostrar reutilización o acumulación hay que repetir A/B sin reiniciar el proceso y comparar POST_AB_2 con POST_AB_1.
5. Picos de CPU anónimo y file-backed ocurren en diferentes momentos; atribución a mmap/allocator/objetos vivos aún abierta. Ninguna operación `/free`, `empty_cache` o `unload_all_models` está justificada por estos datos.
6. El monitor no mide disponibilidad cgroup ni CUDA allocated/reserved del PID; antes de otra corrida revisar margen de RAM y estado idle.

## Siguiente experimento (M-002, único cambio = repetir A→B)

- **Antes de iniciar:** comprobar Comfy PID/health sin jobs activos; RAM disponible (cgroup o /proc/meminfo), GPU usada y monitor externo activo; no instalar ProfilerX, no alterar flags ni modelos. Si el monitor anterior terminó, iniciar una nueva sesión de monitor sin interrumpir ComfyUI.
- Tomar marca PRE_AB_2, ejecutar exactamente la misma pareja Q4→Q6 con misma semilla y configuración, registrar `run_id`/`prompt_id` de A y B y horas de inicio/fin, al terminar marcar POST_AB_2 e intervalo sin tareas de ≥60s.
- Comparar PSS_Anon y RSS después del segundo ciclo con **2.311 GiB anónimo** y **2.829 GiB RSS** del primero; comprobar si vuelve a nivel similar o crece de manera reproducible. Guardar segunda traza.
- Sólo después pasar a ProfilerX opt-in y comparar con baseline, si se requiere atribución por nodo.
