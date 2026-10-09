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
