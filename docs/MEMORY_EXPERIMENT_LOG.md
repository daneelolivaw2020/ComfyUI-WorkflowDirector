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
