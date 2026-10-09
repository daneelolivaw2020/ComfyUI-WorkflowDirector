# Decisión correctiva — dejar de medir y resolver gestión de memoria A→B (2026-10-09)

## Diagnóstico de enfoque

M-001...M-009 consumieron demasiado tiempo clasificando memoria sin proporcionar un mecanismo seguro de liberación. **Detener A3 y la cadena de experimentos smaps/malloc_info.** M-009 acredita Comfy 0.39.0 `--cache-none`, mismo PID 6177, A1 +831.6 MiB PSS_Anon, B1 +15.2 MiB, A2 +76.1 MiB; cargados en `current_loaded_models` 0 al finalizar, CUDA actual aprox. 8 MiB, RAM host disponible ~9.45 GiB. Esto *no* determina si +832MiB se puede recuperar en runtime sin crash; tampoco demuestra meseta o leak. No volver a presentar las pruebas como solución.

## Auditoría de opciones ya existentes, con código consultado

| Recurso | Mecanismo verificado | Consecuencia para este entorno |
|---|---|---|
| [rghvdberg/comfyui-memory-tools](https://github.com/rghvdberg/comfyui-memory-tools/blob/main/memory_backend.py) | `comfy.model_management.unload_all_models()`, `gc.collect()`, `soft_empty_cache()`; botón/nodo. | No es distinto del mecanismo invasivo relacionado con los fallos previos del usuario. No recomendar ejecución en PID activo. |
| [ShmuelRonen/ComfyUI-FreeMemory](https://github.com/ShmuelRonen/ComfyUI-FreeMemory) | normal `torch.cuda.empty_cache()`, `gc.collect()`; agresivo usa `unload_all_models`. | Normal no promete recuperar asignaciones CPU aún vivas; agresivo con riesgos análogos. |
| [VRAM-Hoarder/ComfyUI-Free_model_and_node_cache](https://github.com/VRAM-Hoarder/ComfyUI-Free_model_and_node_cache/blob/main/free_cache_node.py) | Envía petición a endpoint Comfy `POST /api/free` según versión; la rama de Comfy 0.39.0 usa `POST /free` para flags de cola. | No es técnica nueva de allocator; versión/endpoint puede diferir. La respuesta HTTP OK sólo indica aceptación de flags, no prueba de memoria liberada. No recomendar. |
| [neezoy/ComfyUI-UnloadModels](https://github.com/neezoy/ComfyUI-UnloadModels) | Nodos `Unload CPU Models` y `Unload After Sampling`, descargan selectivamente modelos durante grafo. | Candidato para *picos dentro del workflow*, no para RAM residual con manager `loaded_models=0`; compatibilidad con Comfy 0.39.0 + GGUF/LoRA requiere prueba aislada; no prometer seguridad. |
| [mkim87404/ComfyUI-ControlOrder-FreeMemory](https://github.com/mkim87404/ComfyUI-ControlOrder-FreeMemory) | Nodo ordenamiento de ejecución y descargas opcionales. | Interesante para orquestación intragrafo, pero unload sigue siendo invasivo y requiere auditoría de implementación bajo GGUF. |
| [Bloomberg Memray](https://bloomberg.github.io/memray/) | Perfilador **existente** de asignaciones Python+nativas (opción `--native`); [attach](https://bloomberg.github.io/memray/attach.html) sólo observa asignaciones posteriores al attach y requiere inyección/debugger. | Si se exige atribuir +832MiB, usar Memray **en nuevo runtime desechable desde startup**; no attach al servidor del usuario ya cargado ni profiler durante corrida de producción. Costes y compatibilidad Python 3.13 se validan primero. |
| ComfyUI 0.39.0 startup flags | [Código cli_args.py v0.39.0](https://github.com/Comfy-Org/ComfyUI/blob/v0.39.0/comfy/cli_args.py): `--fast-disk`, `--disable-pinned-memory`, `--cache-none` presentes. | Opciones para futuros experimentos de presión RAM, **una por vez**, sin modificar el runtime actual y sin prometer que liberan objetos vivos. `--disable-smart-memory` favorece OFFLOAD hacia RAM, contraproducente para objetivo CPU RAM. |

**Riesgo GGUF**: el GGUF original fijado `city96/ComfyUI-GGUF@6ea2651...` usa `GGUFReader`, mapeos mmap y `GGUFModelPatcher.unpatch_model` delegado al base; pueden existir incompatibilidades al descargar/repachar. No confundir con prueba de que éste sea el causante específico del crash en Colab; no está atribuido.

## Plan operativo real, no nuevas mediciones

**Objetivo A (funcional):** No hacer unload forzado entre A y B mientras ComfyUI tenga suficiente RAM/VRAM y la secuencia complete. Se probaron A y B por separado; falta validación coordinada vía Director Lab. Priorizar que `Run A→B` funcione **sin acciones destructivas**, luego resultados y errores observables. Preservar A/B JSON originales; A `CLIPLoaderGGUF.type=stable_diffusion`, B `flux2`; para pruebas controladas posteriores corregir A *solo en copia*, sin sobrescribir originales.

**Objetivo B (liberación garantizada cuando sea obligatoria):** Implementar como opción de arquitectura una **barrera por procesos** fuera de ComfyUI: controlador padre Colab (no dentro del proceso Comfy) arranca servidor/proceso hijo A, envía API prompt, espera éxito + output durable + cola vacía, solicita terminación limpia del servidor A, verifica salida con timeout y fallback explícito; luego inicia servidor B en nuevo PID y ejecuta B. Terminar un proceso finalizado devuelve al SO sus allocations, sin `malloc_trim`/GGUF unload interno. Coste: overhead de startup, necesidad de restaurar túnel/iframe y manejo de fallos. **No implementado ni validado aún**; no afirmar que hoy existe o que funciona en Colab. Se necesita un supervisor fuera del PID Comfy para no matar su propio workflow. Preferir pruebas en sesión descartable, manteniendo logs y checkpoints.

**Objetivo C (si el usuario exige mismo PID y recupero sin reinicio):** Instrumentar con **Memray** una nueva ejecución controlada *desde startup*, buscando los propietarios y retenedores CPU que `malloc_info` indica como no registrados libres; después intervenir sólo sobre el responsable demostrado. No añadir más medidas sin hipótesis, criterio de éxito y una decisión de parada.

**Criterio de éxito:** A→B finaliza reproduciblemente sin fallos ni OOM, y la RAM se mantiene dentro del límite de Colab; cuando sea requisito restituir RAM al sistema, comprobar delta real de MemAvailable/PSS antes-después del proceso y no sólo `malloc_info`. Evitar forzar unload mientras `current_loaded_models=0`: su beneficio observado al final es incierto.

No alterar código estable, Torch, CUDA, GGUF, ni PR Context #6 por este documento. M-009 se da por **concluido como caracterización, no resuelto como limpieza**. 
