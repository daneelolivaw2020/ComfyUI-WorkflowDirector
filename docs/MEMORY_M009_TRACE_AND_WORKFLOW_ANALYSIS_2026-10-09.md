# M-009 — ZIP de evidencias y comparación de workflows A Q4 / B Q6

**Fecha del experimento:** 2026-10-09 UTC. **Runtime:** nueva cuenta Colab Free, nueva cohorte y PID **6177**, no continuo respecto de PID 16744 de M001–M003.

**Fuentes primarias:** tres adjuntos facilitados por el usuario en la conversación (no subidos al repositorio): `M009_COMPLETE_EVIDENCE.zip`, `pesado A Q4.json`, `pesado B Q6.json`. Contenido JSON inspeccionado. No reproducir prompts del usuario ni adjuntar workflows al repositorio sin consentimiento explícito.

## Integridad del ZIP

`M009_COMPLETE_EVIDENCE.zip` contiene siete registros:
1. `M009_PRE_COMFY.json` — antes de arrancar Comfy, 06:22:42.257Z.
2. `M009_COMFY_COLD.json` — Comfy sin jobs, 06:33:04.363Z.
3. `M009_POST_A.json` — POST_A 06:42:24.232Z y settled 06:43:24.301Z.
4. `M009_POST_A_MODEL_STATE.json` — memoria del manager y CUDA.
5. `M009_PRE_B.json` — 06:48:23.711Z.
6. `M009_POST_B.json` — 06:54:14.736Z.
7. `M009_POST_B_SETTLED.json` — 06:55:14.799Z.

Todos los registros del proceso tienen **PID 6177**. Comfy 0.39.0, `--cache-none`, T4, glibc 2.39, instrumentación `/workflowdirector/memory/glibc` habilitada. La línea base pre-Comfy no tiene PID activo.

## Memoria comparada exacta

| Estado | RSS GiB | PSS_Anon GiB | PSS_File GiB | glibc heap entries | glibc arena system current MiB | glibc central free fast+rest MiB |
|---|---:|---:|---:|---:|---:|---:|
| COLD | 1.2874 | 0.7447 | 0.5163 | 16 | 300.61 | 16.28 |
| POST_A_SETTLED | 2.1020 | 1.5568 | 0.5148 | 16 | 1206.41 | 58.72 |
| PRE_B | 2.1020 | 1.5568 | 0.5148 | 16 | 1207.97 | 60.26 |
| POST_B inmediato | 2.0902 | 1.5716 | 0.4887 | 16 | 1212.78 | 65.00 |
| POST_B_SETTLED | 2.0902 | 1.5716 | 0.4887 | 16 | 1214.61 | 66.81 |

**Deltas:**
- COLD → A (asentado): PSS_Anon **+0.8121 GiB (831.59 MiB)**; glibc arena system.current **+905.79 MiB**; glibc listas centrales libres **+42.43 MiB**.
- A asentado → B asentado: PSS_Anon **+0.0148 GiB (15.16 MiB)**, RSS **-0.0118 GiB (~-12.08 MiB)**, PSS_File **-0.0261 GiB**, arenas glibc **+8.2070 MiB**, freelists glibc **+8.0948 MiB**.
- PRE_B → POST_B_SETTLED más estrecho: arenas glibc **+6.6445 MiB**, freelists **+6.5526 MiB**; diferencia ~0.09 MiB. `system.current - fast/rest` no equivale a suma de objetos vivos o resident bytes.
- CUDA `peak_allocated_since_reset_gib` después de A **7.0756 GiB**, después de B **9.1703 GiB** (es high water desde reset, no instantáneo ni prueba del tiempo/pico exacto de B); tras B `allocated_gib = 0.0079`, `reserved_gib = 0.0312`, modelos en `comfy.model_management.current_loaded_models = 0`. La evidencia no identifica otros objetos CPU referenciados.
- Sistema MemAvailable COLD 10.3184 GiB, POST_A 9.5246 GiB, POST_B 9.4835 GiB. Cambios de memoria del host no atribuibles exclusivamente al PID.

**Interpretación:** B provoca muy poco crecimiento residual vs A aunque incrementa el máximo histórico de CUDA asignada. Es **compatible** con reutilización/estabilización del allocator tras primera carga, pero solo dos cargas distintas; no establece meseta universal, ausencia de fuga ni liberabilidad de PSS anónima. La observación de glibc sugiere que el grosor de +0.8GiB no está en freelists centrales visibles (aumento de solo ~42MiB), pero falta atribución de objetos nativos retenidos y cachés por hilo. El manager de modelos vacío ≠ ausencia de referencias fuera del manager.

## Comparación precisa de los workflows suministrados

Los archivos guardados contienen **15 nodos y 19 links** cada uno, con **idéntica topología (IDs/tipos/enlaces)**. Se conservaron:
- Sampler Euler, 4 pasos, CFG=1, semilla fija 261.
- FluxResolutionNode 1.0 MP, relación 7:9 portrait, divisible por 64, `EmptyFlux2LatentImage` batch 1 (width/height por enlaces); `Flux2Scheduler` y VAEDecode.
- `flux2-vae.safetensors`, LoRA `klein_snofs_v1_1.safetensors` al 100% (`strength=1`) mediante rgthree Power Lora.
- Mismo prompt positivo y negativo, mismo grafo de SaveImage. **No reproducir contenido de prompts**.

**Tres diferencias funcionales exactas (widget values):**
1. Nodo 98 `UnetLoaderGGUF`: A `flux-2-klein-9b-Q4_0.gguf`; B `flux-2-klein-9b-Q6_K.gguf`.
2. Nodo 99 `CLIPLoaderGGUF`: A `Qwen3-8B-Q4_K_S.gguf`; B `Qwen3-8B-Q6_K.gguf`.
3. **Nodo 99 `CLIPLoaderGGUF.type`: A `stable_diffusion`; B `flux2`.** Esta tercera diferencia es un potencial confusor importante, no solo cuantización. La versión PIN de GGUF `city96/ComfyUI-GGUF` commit `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` resuelve la cadena hacia `comfy.sd.CLIPType` (https://github.com/city96/ComfyUI-GGUF/blob/6ea2651e7df66d7585f6ffee804b20e92fb38b8a/nodes.py); la lógica ComfyUI `v0.39.0/comfy/sd.py` tiene rama explícita `CLIPType.FLUX/FLUX2` para codificador Qwen3VL de Klein y otra rama para tipos restantes (https://github.com/Comfy-Org/ComfyUI/blob/v0.39.0/comfy/sd.py). Por tanto, esta diferencia **puede cambiar encoder/tokenizador**, semántica de inferencia, allocations y resultados; **no es únicamente cosmética**. No se ha probado si A original falló o obtuvo outputs correctos; no inferir. Se aconseja crear **una copia de A** con tipo `flux2`, conservar archivo A original intacto y tratar cualquier reejecución como nuevo experimento, sin mezclar con el baseline frío de esta cohorte.

Otros cambios de metadatos (id gráfico, viewport) son editoriales.

## Limitaciones y decisiones

- Workflow A fue ejecutado desde WorkflowDirector Lab; B **directamente desde ComfyUI**, no se validó coordinación A→B dentro del Director en M009.
- No hay trazas periódicas de picos RSS para este nuevo runtime ni IDs exactos Comfy; los registros son puntos pre/post.
- **Próximo paso sin nuevos jobs ni cambio de librerías**: registrar el confusor `CLIPLoaderGGUF.type` y una lectura puntual read-only de `/proc/6177/smaps` para atribuir cuánta PSS/RSS anónima actual cae en heaps secundarios de 64MiB alineados, vs heap principal y otras mmap. Esta prueba solo demuestra geometría/residencia, no dueños ni reclamabilidad.
- Para encontrar propietarios reales de memoria marcada en uso por glibc, hará falta instrumentación distinta con coste/safety delimitados (allocator hooks en runtime nuevo / ProfilerX para etapas + correlación / revisión referencias de nodes), no `malloc_trim()`, `/free`, `empty_cache()` ni unload ciego. No repetir ciegamente A/B ni tocar Context PR#6.
