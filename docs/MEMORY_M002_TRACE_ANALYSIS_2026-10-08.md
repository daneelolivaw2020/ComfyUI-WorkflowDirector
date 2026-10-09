# M-002 — Segunda corrida Klein A→B sin reiniciar, análisis ZIP completo

**Fecha de adquisición:** 2026-10-08 CDMX / 2026-10-09 UTC.
**Estado:** segunda corrida observacional realizada; el usuario aportó marcadores POST_AB_2 y POST_AB_2_SETTLED, picos y archivo `M002_memory_AB.zip`. La finalización correcta de ambos jobs en esta segunda corrida **no está confirmada por IDs/estados terminales**; los marcadores POST_AB_2 y la vuelta a reposo son evidencia indirecta. Primera corrida M-001 A/B sí confirmada por el usuario.

**Fuente:** ZIP `M002_memory_AB.zip` compartido en la conversación; contiene `M002_20261009_052124.jsonl` y `M002_20261009_052124_markers.jsonl`. El ZIP está adjunto en la conversación, no en el repositorio. Continuidad de M-001 en [MEMORY_M001_TRACE_ANALYSIS_2026-10-08.md](MEMORY_M001_TRACE_ANALYSIS_2026-10-08.md).

## Integridad y entorno de medición
- **248 muestras** desde **05:21:24.875456Z** hasta **05:30:05.933825Z**, ~8m41s. Cadencia mediana ~2.088s; máximo intervalo ~2.338s; sin brechas mayores de 3s.
- **PID 16744** en todas las muestras; coincide con M-001 (524 muestras). Mismo proceso ComfyUI, sin evidencia de reinicio entre adquisiciones.
- Monitor externo read-only basado en `scripts/memory_watch.py`; registra /proc smaps_rollup + NVML global cada ~2s; sin import Torch y sin cleanup. Sin ProfilerX.
- ComfyUI 0.39.0, WorkflowDirector 0.0.7-dev, `--cache-none`, `--reserve-vram 0.8` confirmados antes de M-001.
- Memoria del sistema reportada antes de M-002: 12.67 GiB total, 8.78 GiB MemAvailable, Director ready=true y active_run_id=null. La cifra 0.47 GiB de memory.current de la celda del notebook no representa el RSS del proceso Comfy y queda excluida.
- **Sin IDs prompt/run ni tiempos de job disponibles** para asignación por workflow.

## Marcadores extraídos del ZIP

| Métrica | PRE_AB_2 (05:21:29.741Z) | POST_AB_2 (05:27:52.938Z) | POST_AB_2_SETTLED (05:28:52.939Z) |
|---|---:|---:|---:|
| RSS, GiB | 2.829090 | 2.511574 | 2.511574 |
| PSS, GiB | 2.813514 | 2.499040 | 2.499040 |
| PSS_Anon, GiB | 2.311440 | 2.377937 | 2.377937 |
| PSS_File, GiB | 0.488399 | 0.107427 | 0.107427 |
| PSS_Shmem, GiB | 0.013676 | 0.013676 | 0.013676 |
| VRAM GPU global, MiB | 189 | 189 | 189 |

Las marcas leían la **última muestra escrita**, no una captura síncrona exacta; sample_utc del marcador inicial 05:21:28.992Z, POST 05:27:51.853Z, SETTLED 05:28:51.586Z.

**Diferencias M-002 POST menos PRE:** RSS -0.317516 GiB (~ -325 MiB), Pss_Anon +0.066498 GiB (~ +68 MiB), Pss_File -0.380972 GiB (~ -390 MiB), VRAM global sin cambio. El descenso de RSS lo domina la caída de file-backed residente; *no atribuirlo a unload dirigido*.

## Picos registrados en M-002 (no simultáneos)

| Métrica | M-002 máximo | UTC | M-001 máximo | Δ M-002 − M-001 |
|---|---:|---|---:|---:|
| RSS, GiB | 8.686127 | 05:26:29.031Z | 8.898037 | -0.211910 GiB (~ -217 MiB) |
| PSS, GiB | 8.673594 | 05:26:29.031Z | 8.882408 | -0.208814 GiB |
| PSS_Anon, GiB | 7.214367 | 05:26:33.408Z | 7.137981 | +0.076386 GiB (~78 MiB) |
| PSS_File, GiB | 4.724025 | 05:23:58.411Z | 5.474691 | -0.750666 GiB (~ -769 MiB) |
| VRAM global, MiB | 12125 | 05:24:45.510Z | 12121 | +4 MiB |

No sumar máximos de distintas épocas. Muestreo ~2 s puede omitir picos cortos.

## Segmentación exploratoria: GPU global >1000 MiB (no equivalencia con job)

- 05:22:52.813–05:23:07.694Z: bloque breve, 8 muestras, pico 5373 MiB.
- 05:23:49.898–05:24:58.272Z: bloque de 33 muestras, pico 12125 MiB.
- 05:25:25.905–05:27:04.265Z: bloque de 46 muestras, pico 12029 MiB.
- Hay periodos de GPU baja entre los bloques. Una fracción de los intervalos de preparación/carga se refleja principalmente en RSS/PSS, no en GPU. **Tres bloques GPU no significan tres jobs**; sin IDs y fronteras nativas no atribuir a Q4/Q6 con certeza.

## Estado estable tras última actividad

- Del **05:27:06.434Z al 05:30:05.934Z**, 88 muestras, RSS **2.511574 GiB**, PSS_Anon **2.377937 GiB**, GPU global a nivel de reposo ~189 MiB. RSS y anónimo constantes a resolución del instrumento; variación `PSS_File` ~0.004 MiB.
- M-001 terminó con RSS 2.829090 / PSS_Anon 2.311440 / PSS_File 0.488346 GiB y GPU global 189 MiB; habían permanecido estables ~5m16s.
- **Interpretación:** no aparece acumulación grande en RSS total después de dos ciclos; sí pequeño incremento neto de anónima ~68 MiB. Dos ciclos **no** bastan para estimar pendiente/repetibilidad; distinguir caching amortizado, allocators y objetos vivos requiere repetición y posterior atribución.
- Ninguna prueba demuestra que se hayan liberado todos los modelos, que pueda descargarse memoria adicional sin riesgo, o que un mecanismo de cleanup sea necesario.

## Próxima acción: experimento M-003 sin ProfilerX todavía

1. Comprobar Comfy sigue PID 16744 con `--cache-none`, servicio ready + active_run_id null, RAM MemAvailable >= margen prudente según picos y VRAM global en reposo. Si cambia el PID, **parar**: no sería tercer ciclo mismo proceso.
2. Conservar los archivos M-001/M-002 y rotar a un **nuevo** `memory_watch.py` con duración suficiente; marcar PRE_AB_3, POST_AB_3, POST_AB_3_SETTLED a >=60s, recoger IDs nativos A/B si existen.
3. Repetir **exactamente los mismos** A y B, sin cambiar prompts, semilla, modelos, flags, plugins y sin `/free`/unload manual.
4. Comparar **PSS_Anon final** contra 2.311440 (M-001) y 2.377937 GiB (M-002) y **RSS final** contra 2.829090 / 2.511574 GiB; buscar tendencia sostenida vs meseta.
5. Si M-003 muestra incremento relevante y reproducible, pasar a atribución por nodo/objetos con ProfilerX **como experimento aislado**, entendiendo interferencia con contadores de pico torch. Si se estabiliza, ampliar pruebas con ciclos y barreras POST_A / PRE_B antes de diseñar remediación.

**NO activar remediaciones destructivas, ni afirmar diagnóstico de fuga a partir de esta serie.**
