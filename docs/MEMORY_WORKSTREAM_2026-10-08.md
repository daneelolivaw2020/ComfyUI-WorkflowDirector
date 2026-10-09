# MEMORIA — Plan maestro, decisiones y bitácora de continuidad
**Inicio:** 2026-10-08, zona horaria de trabajo America/Mexico_City.
**Rama activa para este frente:** `feature/memory-diagnostics`, basada en la rama de pruebas previamente aceptada `feature/colab-acceptance`.
**Estado:** trabajo ACTIVO, fase M0/M1 (diagnóstico, todavía no solución final).
**PR de Context universal:** #6, **PAUSADO** en `feature/universal-context-nodes` y documentado en
[HANDOFF_CONTEXT_PAUSADO_2026-10-08.md](https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector/blob/feature/universal-context-nodes/docs/HANDOFF_CONTEXT_PAUSADO_2026-10-08.md).
No modificar Context hasta que el usuario solicite retomarlo.

## 1. Por qué existe el trabajo de memoria

**Problema de producto**: en Colab Free estándar + T4, un workflow de ComfyUI (modelos GGUF Klein, encoder Qwen, LoRAs, sampler, VAE) puede terminar correctamente pero dejar RAM/VRAM ocupada; los intentos anteriores de hacer unload manual o usar `/free` provocaron caídas completas del runtime. Necesitamos encadenar workflows PESADOS e independientes A→B→C sin reiniciar el kernel y sin retener recursos de modelos previos que no forman parte explícita de Context.

**Objetivo funcional (no confundir con reducir memoria a cero)**:
- Tras completar A, conservar sólo Context confirmado y la línea base imprescindible de runtime/sistema, además de las asignaciones que sean realmente compartidas/reutilizables y cuya existencia conozcamos.
- Recuperar tanta memoria RAM/VRAM de A como sea posible **sin destruir el proceso**.
- Medir dos barreras: POST_A y PRE_B; impedir B cuando el estado es inseguro o insuficiente, en vez de iniciar y fallar por OOM.
- Diagnosticar causas específicas antes de desarrollar cleanup dirigido; si no es posible liberarlo en un proceso, valorar aislamiento entre procesos como estrategia separada.
- Mantener el objetivo obligatorio: **Google Colab Free, NVIDIA T4, RAM estándar**; no exigir A100/L4, High-RAM, CUDA/torch diferentes ni extensiones de pago.

## 2. Qué sabemos, qué creemos, qué falta demostrar

**Observado previamente (NO reproducido aún en este frente):**
- Con caché predeterminada se observaron valores cercanos a 8.7 GiB RSS después de ciertos trabajos.
- Con `--cache-none`, en las pruebas anteriores se observó cerca de 2.6–2.8 GiB RSS y cerca de 0.18 GiB de VRAM usada tras algunos jobs.
- Klein Q4 y Q6 han funcionado individualmente; secuencias específicas A→B y Context ligero se ensayaron en la rama anterior.
- La descarga agresiva produjo crashes. No volver a activarla a modo de experimento casual.
Estos números **no** prueban fuga ni representan el requisito contractual del producto. PyTorch/Python/Comfy/CUDA y file-backed GGUF mmap explican memoria base y recuperable.

**Hipótesis a comprobar con evidencia separada:**
H1. Caché de resultados o referencias Comfy/Python siguen reteniendo modelos.
H2. mmap de ficheros GGUF eleva RSS/PSS_File pero no representa fuga anónima.
H3. El allocator CPU/torch reserva arenas aunque no queden objetos de modelo vivos.
H4. Algunos nodos/extensiones mantienen referencias circulares o globales.
H5. Parte de la VRAM es reserva reutilizable de PyTorch o contexto CUDA, no tensor vivo.
H6. Context CPU copia datos de forma segura, pero sus picos temporales y duplicaciones deben aislarse en mediciones posteriores.
**No dar ninguna hipótesis por probada sin registros comparables.**

## 3. Entorno reportado por el usuario (NO alterar al instalar un profiler)

- Python **3.13.15**
- **723 paquetes Python** detectados (dato ambiental, no es métrica de memoria).
- PyTorch **2.11.0+cu130**
- CUDA informada por PyTorch **13.0**
- ComfyUI **v0.39.0** y frontend **1.53.10**: versión validada en la fase anterior; **volver a verificar la versión viva**, no asumirla de la instalación actual.
- Arranque experimental: `--cache-none` y puerto 8188; verificar línea de comando real del proceso.
- Ningún cambio a `pip install torch`, `pip install --upgrade torch`, toolkit de CUDA o flags de descarga/destrucción.

## 4. Herramientas existentes: decisión y criterios

### M0 — Instrumentación sin instalar un custom node
Usar:
- WorkflowDirector existente `workflowdirector/memory.py` y observaciones post-job: RSS, PSS/Pss_Anon/Pss_File, cgroup available, torch CUDA allocated/reserved, GPU used/free, número de LoadedModel entries.
- Nuevo observador **externo, read-only**, `scripts/memory_watch.py` en esta rama: se ejecuta por separado desde Colab, sin importar torch, sin ejecutar `/free`, `empty_cache`, ni `unload_all_models`. Consulta el **PID de Comfy**, smaps_rollup/statm de Linux y `nvidia-smi` global a intervalos (por defecto cada 2 s) a JSONL en `/content`.
- Ventaja: muestrea picos que ocurren **mientras** ejecuta A; la muestra es periódica, no exacta al milisegundo.
- Limitación: JSONL no atribuye bytes a objetos ni refleja memoria PyTorch del proceso desde fuera; GPU nvidia-smi es global, no propiedad exclusiva de Comfy.

### M1 — Instrumentar automáticamente por nodo: ProfilerX
**Repositorio:** https://github.com/ryanontheinside/ComfyUI_ProfilerX
**Pin de investigación (verificado en la consulta):** `007bc3439b4f73c2e60099812d0c371b7e97d2c8`.
`requirements.txt`: `psutil>=5.9.0`; declara Python 3.8+. No requiere por sí mismo reinstalar Torch.
Permite `promptId`, `nodeId`, `nodeType`, start/end, RSS before/after, PyTorch CUDA allocated before/after, pico CUDA y hit/miss de caché; `GET /profilerx/stats` después de que el job termine.
**No añade nodos al workflow:** usa ProgressHandler.
**Advertencias del código inspeccionado**:
- El README dice uso de APIs oficiales, pero `__init__.py` también parchea `progress.reset_progress_state` y el binding `execution.reset_progress_state` para reinyectar el handler; no es literalmente «sin monkey-patches».
- Reinvoca `torch.cuda.reset_peak_memory_stats()` por nodo; por eso las métricas de picos de WorkflowDirector pueden verse afectadas y no deben combinarse ingenuamente como si fueran la misma época de medición.
- Sus «picos RAM» se construyen con RSS en puntos discretos, no con seguimiento continuo intranodo.
- No llamar a `GET /profilerx/stats` durante una ejecución: `handler.flush()` puede finalizar el registro en curso; consultarlo **sólo al finalizar el job nativo**.
- Existe el fichero histórico `prestartup.py` con hooks más intrusivos; NO habilitarlo ni renombrarlo `prestartup_script.py`.
**Resultado hasta ahora:** compatibilidad de interfaz `ProgressHandler` inspeccionada contra tagged Comfy 0.39.0, pero **sin prueba real de import/ejecución con PyTorch 2.11/cu130**. Usarlo **en una corrida experimental controlada**, comparando contra baseline sin profiler.

### M2 — Opción posterior, no instalar simultáneamente: Resource Snapshot
https://github.com/PBandDev/comfyui-resource-monitor
Pin consultado: `5e437477656adcab2ecdd0caedc5060a265cbf91`.
Pyproject v1.0.4 `requires-python>=3.12` y deps `psutil>=7.2.2`, `nvidia-ml-py>=13.590.48`.
Tu Python 3.13.15 satisface el rango declarado. **No concluimos** que la integración ComfyUI 0.39/front 1.53.10 esté probada.
Nodo `PBandDev/Resource Monitor → Resource Snapshot` tiene `AnyType` passthrough y outputs de métricas. Su RAM es **psutil.virtual_memory del sistema**, NO RSS del proceso; GPU usada es **NVML global**. Su dashboard trae controles **Unload Models** y **Free Memory**; ocultarlos en ajustes `Show Clear Buttons=false` y **nunca pulsarlos en nuestro experimento**.
Se evalúa únicamente si ProfilerX + observador de PID dejan dudas sobre una etapa concreta y se desea marcar un punto con paso directo en el grafo. Instalarlo solo, en un experimento distinto, no con otros profilers.

### M3 — Herramientas de atribución selectiva (sin instalar hoy)
- Registro interno `comfy.model_management.current_loaded_models` (weakrefs): metadata de objetos, `id` efímero por proceso, tipo, estimaciones cargado/offloaded. *Sólo consulta*: no guardar fuertes referencias a patchers/modelos.
- PyTorch `torch.cuda.memory._record_memory_history(..., max_entries=bounded)` + `_dump_snapshot` y https://pytorch.org/memory_viz. Sólo allocator Torch; snapshots pueden tener gran sobrecoste.
- `tracemalloc` para bloques Python (no C++/mmap completo).
- Memray para memoria CPU nativa, sólo en runtime desechable y si justificado.
- `/proc/PID/smaps` para rutas y mapas de los ficheros .gguf que ocupan Pss_File.
**Evitar primera fase:** extensiones MemoryManagement que llaman `unload_all_models`, nodos unload, HardDelete, `/free`, Datadog que parchea el ejecutor, cuatro extensiones simultáneas.

## 5. Plan de trabajo experimental (fases y criterios)

**D0 — Verificación de arranque antes de cambios**: ComfyUI 0.39, front 1.53, flag `--cache-none`, puerto/PID reales; RAM/VRAM libre. No añadir nodos.

**D1 — Línea base sin profiler**: levantar observador externo read-only. Esperar unos segundos en idle; ejecutar exactamente el mismo A Klein Q4 (sin unload), B Klein Q6 cuando proceda con el Director; registrar tiempos y estados de Jobs, RSS/PSS anon/file, VRAM global y cuda allocator de las observaciones nativas en cada barrera. Guardar `/content/workflowdirector_memory_watch.jsonl` y números con IDs. Hacer al menos 2–3 ciclos comparables si la sesión lo tolera. Si la memoria residual es estable, no etiquetar como fuga.

**D2 — ProfilerX aislado**: una vez recogido D1 y con los trabajos terminados, instalar sólo pin ProfilerX como plugin custom_node en la **ruta REAL** del Comfy del Colab, verificar requisitos y reiniciar sólo el proceso Comfy con los flags anteriores. Probar primero un trabajo pequeño, comprobar `/profilerx/stats` **tras** completarlo y cruzar nodeId/promptId. Después repetir el mismo A/B y comparar efectos. Si hay incompatibilidad, eliminar sólo carpeta ProfilerX y reiniciar Comfy; **no desinstalar PyTorch**.

**D3 — Clasificar retención**:
- `Pss_File` alto → mmap GGUF, .so, etc.; analizar rutas si crece, sin asumir fuga.
- `Pss_Anon` alto y progresivo → objetos CPU/nativos/allocator, investigar por nodos y registro de modelos.
- Torch CUDA allocated alto → tensores vivos, PyTorch Snapshot acotado.
- Torch reserved alto con allocated bajo → allocator reutilizable.
- NVML alto y torch bajo → CUDA de otras bibliotecas/procesos, contexto.
- Comfy LoadedModel entries presentes → pistas de registro/referencias, NO prueba automática de leak.
No descargar nada hasta identificar el propietario.

**D4 — Diseñar dos barreras**: POST_A + PRE_B, con observación y respuesta calibrada. Una segunda «barrida» ciega puede repetir el mismo fallo sin liberar referencias vivas. Establecer criterio de suficiente memoria (incluyendo costo esperado de B) y mecanismo fail-closed sin `/free`.

**D5 — Remediación y regresiones**: desarrollar una limpieza concreta para el dueño identificado, o aislamiento de procesos como fallback si no es viable en un único servidor Comfy. Repetir exactos Q4→Q6 y cuantificar mejoras **con y sin ProfilerX**. No fusionar cambios sólo por CI.

## Bitácora de ejecución persistente

**Archivo de resultados:** [MEMORY_EXPERIMENT_LOG.md](MEMORY_EXPERIMENT_LOG.md). Contiene la entrada M-000 con el estado real (sin pruebas de Colab en este frente) y la plantilla para los experimentos M-001, M-002, etc. Actualizar la bitácora después de **cada sesión**; este plan conserva el «por qué», mientras la bitácora conserva los resultados.

## 6. Reglas de documentación obligatorias para próximas sesiones

En este documento o una nueva bitácora enlazada, al terminar cada experimento agregar:
- Fecha/hora local; objetivo/Hipótesis (H1..H6); por qué el experimento discrimina entre alternativas.
- Revisión git/branch de WorkflowDirector y extensiones (SHAs), Comfy/frontend/Python/Torch/CUDA/driver, flags, T4/RAM, archivo notebook exacto.
- Workflow A/B, IDs nativos, nodos relevantes, rutas de logs y JSONL, orden de ejecución, sin/ con profiler.
- Baseline/POST_A inmediata/settled/PRE_B/POST_B en RSS,PSS, Pss_Anon, Pss_File, cgroup disponible, Torch CUDA allocated/reserved, NVML used; picos observados vs puntuales.
- Tabla de diferencias, explicación de mediciones desconocidas, hipótesis aceptada/rechazada/no concluyente, problemas de la propia instrumentación.
- Cambios realizados, pruebas, cómo revertirlos, preguntas abiertas y **siguiente única acción**.

**Nunca** usar términos «fuga», «liberado totalmente» o «crash resuelto» sin evidencia reproducible y diferenciación entre cache y memoria retenida. Un chat nuevo debe leer este archivo y la guía antes de trabajar.

## 7. Estado real al escribir

- [x] Abrir rama propia `feature/memory-diagnostics` desde baseline aceptado.
- [x] Investigar ProfilerX, Resource Monitor y herramientas PyTorch/Linux usando código fuente.
- [x] Recibir versiones actuales del Colab: Py 3.13.15, torch 2.11.0+cu130, CUDA 13.0, 723 paquetes.
- [x] Crear `scripts/memory_watch.py` observador externo de sólo lectura y tests.
- [x] CI del frente verificada para el commit de código inicial (Core tests, Python 3.11/3.13; los commits de documentación posteriores no validan Colab).
- [x] Verificar Comfy vivo + flags (Comfy 0.39.0 / PID 16744 / --cache-none activo; versión de frontend pendiente de lectura independiente).
- [x] Primera corrida baseline D1 A→B exitosa, sin plugins nuevos, con traza completa M-001 (524 muestras; análisis en [MEMORY_M001_TRACE_ANALYSIS_2026-10-08.md](MEMORY_M001_TRACE_ANALYSIS_2026-10-08.md)). **Falta repetición M-002 antes de concluir sobre retención.**
- [ ] Instalar/probar ProfilerX en D2 y registrar versión pin.
- [ ] Evaluar registro weakrefs/modelos y snapshots específicos.
- [ ] Diseñar/remediar barrera doble (POST_A y PRE_B).
- [ ] Regresión A→B pesada en Colab Free T4.
- [ ] Context permanece pausado, protegido en PR #6.

## 8. Enlaces y mensajes para otro chat

**Guía operacional (instalación, celdas Colab, rollback):**
`docs/MEMORY_COLAB_RUNBOOK.md` de esta misma rama.

**Recuperar este trabajo:**
> Estoy trabajando en `daneelolivaw2020/ComfyUI-WorkflowDirector`. Context universal está pausado en el PR #6. Lee íntegro `docs/MEMORY_WORKSTREAM_2026-10-08.md` y `docs/MEMORY_COLAB_RUNBOOK.md` en la rama `feature/memory-diagnostics`. Nuestro objetivo prioritario es identificar la RAM/VRAM retenida entre workflows independientes Klein Q4/Q6 en Colab Free T4 y construir una barrera doble SEGURA; las pruebas de unload directas hacían crashear Comfy. Usa las versiones reales actuales del Colab y nunca reinstales Torch/CUDA para meter un profiler. Documenta decisiones y evidencias nuevas en GitHub. Continúa desde D0/D1 y no vuelvas a implementar Context.

**Fuentes upstream**:
- https://github.com/ryanontheinside/ComfyUI_ProfilerX
- https://github.com/PBandDev/comfyui-resource-monitor
- https://github.com/Comfy-Org/ComfyUI/blob/v0.39.0/comfy_execution/progress.py
- https://github.com/Comfy-Org/ComfyUI/blob/v0.39.0/comfy/model_management.py
- https://docs.pytorch.org/docs/stable/torch_cuda_memory.html
- https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector/blob/feature/universal-context-nodes/docs/EXISTING_MEMORY_DIAGNOSTICS_RESEARCH_2026-10-08.md
