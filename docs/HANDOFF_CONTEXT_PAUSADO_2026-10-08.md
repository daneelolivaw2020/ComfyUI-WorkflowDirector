# HANDOFF — Context universal de WorkflowDirector (PAUSADO)
**Fecha de corte:** 2026-10-08 (CDMX)
**Propósito:** conservar TODO el estado de decisión, implementación, pruebas y pendientes de Context para retomarlo desde otro chat sin reinterpretar la intención del usuario.
**Estado:** PAUSADO por decisión explícita del usuario. **Trabajo activo: diagnóstico, identificación, atribución y gestión segura de memoria RAM/VRAM**. No continuar implementando Context hasta que el usuario decida reanudarlo.

> **Instrucción para un nuevo chat:** leer este archivo COMPLETO y los enlaces de la sección «Fuentes de verdad» directamente en GitHub antes de modificar código. No depender del resumen conversacional. Este handoff es una guía, pero prevalece el estado del repositorio al retomarlo y la intención del usuario. Distinguir lo probado de lo solamente implementado.

## 0. Resumen ejecutivo / intención que NO hay que perder

**WorkflowDirector no es solamente un ejecutor A→B ni un sistema de variables compartidas.** Su objetivo principal es permitir **workflows grandes e independientes** en **Colab Free, T4, RAM estándar**, utilizando la misma memoria física secuencialmente. Al terminar cada workflow, deben quedar como datos de la ejecución anterior **sólo los valores explícitamente conservados en Context**, además del consumo base inevitable de Python/ComfyUI/PyTorch/CUDA; se busca recuperar tanta RAM/VRAM reutilizable como sea posible, con verificación antes de B. No afirmar que se puede reducir físicamente todo a cero.

El usuario quiere **sólo DOS nodos públicos universales**, con el comportamiento natural de Set/Get:
1. **PUT INTO CONTEXT**: clave textual `key`, entrada compatible con **cualquier tipo de socket de ComfyUI** y, preferentemente, passthrough de salida con el mismo tipo.
2. **GET FROM CONTEXT**: clave textual `key`, salida que pueda conectarse a cualquier consumidor del workflow posterior.

**No** limitar la UX a STRING/IMAGE/LATENT, porque las extensiones introducen CONDITIONING, AUDIO, VIDEO, custom types y estructuras futuras. **No** crear un nuevo par de nodos por tipo. Usar los mecanismos nativos **`MatchType` / `AnyType` de ComfyUI V3**. Las extensiones KJNodes Set/Get, rgthree y Anything Everywhere demostraron la conveniencia del patrón, pero sus conexiones virtuales en un mismo prompt **no** resuelven transferir datos entre **jobs nativos independientes**. **No copiar el código GPL de KJNodes**: aprovechar las APIs nativas de Comfy.

Distinción esencial:
- **Conector universal:** admite enlaces visuales de muchos tipos.
- **Transporte seguro:** captura / conserva / reconstruye el dato REAL entre dos ejecuciones separadas.
- **Compatibilidad semántica:** GET debe entregar exactamente el tipo correcto al consumidor, no sólo un objeto Python con forma parecida.
- **Residencia:** Context decide dónde reside (CPU RAM ahora, scratch/durable más adelante), pero **NO debe retener modelos vivos u objetos que bloqueen el vaciado de RAM/VRAM**.

## 1. Fuentes de verdad y estado Git

Repositorio: https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector

- **Rama de pruebas anteriormente aceptada:** `feature/colab-acceptance`, commit `62d43b1ddb169deba69135d5c7ebbd420d1ba5e0`. **Mantener intacta**.
- **Rama experimental Context universal:** `feature/universal-context-nodes`, derivada de la anterior; antes de crear este documento la punta era `830a40161f1b5f081c4b226ce8c7ac0032e83c92`. La punta habrá avanzado por los commits de documentación; consultar GitHub al reanudar.
- **PR #6 BORRADOR**, base `feature/colab-acceptance`: https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector/pull/6
- **No merge a `main` ni a la rama aceptada hasta aceptación real del universal en Colab T4**.
- Última CI previamente verificada antes del handoff: éxito en Python 3.11/3.13 para commit `830a40161f1b`. No confundir CI con prueba end-to-end en GPU.

### Documentos que hay que leer en orden al reanudar

1. **Éste:** `docs/HANDOFF_CONTEXT_PAUSADO_2026-10-08.md`.
2. `docs/UNIVERSAL_CONTEXT_DESIGN.md` — nodos nuevos, contrato y puertas de aceptación.
3. `docs/UNIVERSAL_CONTEXT_DOUBLE_AUDIT_2026-10-08.md` — auditoría independiente arquitectura-first y código-first; hallazgos, bloqueos.
4. `docs/CONTEXT_MVP_IMPLEMENTATION.md` — seis nodos typed y funcionamiento transaccional.
5. `docs/CONTEXT_RESIDENCY.md` — RAM/SCRATCH/DURABLE, clave lógica, objetos que NO se permiten.
6. `docs/DOUBLE_AUDIT_CONTEXT_2026-10-08.md` — fallos de contabilidad de memoria y casos de abandono/cancelación corregidos anteriormente.
7. `docs/ARCHITECTURE_REVIEW_2026-10-07.md`, `docs/MEMORY_BARRIER_STRATEGY.md`, `docs/VALIDATION_PLAN.md`, `docs/COMPATIBILITY.md`.
8. **Trabajo activo de memoria:** `docs/EXISTING_MEMORY_DIAGNOSTICS_RESEARCH_2026-10-08.md` — ProfilerX, Resource Snapshot, modelos vivos, /proc/smaps, PyTorch CUDA snapshots, contraindicaciones.

## 2. Arquitectura decidida (mantener)

- Orquestación en el **backend service**, **fuera** de PromptExecutor, nunca en un nodo que se autobloquee esperando nuevos prompts.
- Cada workflow A/B/C es un **job nativo independiente**. Un RunPlan contiene snapshots inmutables; cada job tiene `prompt_id` único/determinista; trabajos secuenciales, terminal status antes de avanzar. Frontend tab/canvas actúa como preparación y observación; backend posee la ejecución.
- Context es **run-scoped**. Claves arbitrarias UTF-8 de máximo 128 caracteres (sin controles ni bordes en blanco), `key -> kind/value` hoy.
- Durante A, los PUT se **stagean** en `StepPatch` y no son visibles todavía. **Commit atómico** de todas las escrituras únicamente después de `COMPLETED` del job. Fail/cancel/timeout/ambiguous: **no commit**. Una sola escritura por key por step; duplicados literales detectados antes y claves dinámicas duplicadas rechazadas en tiempo de ejecución.
- GET lee sólo valores **ya confirmados de pasos anteriores**, y devuelve copia independiente (no compartir referencia modificable).
- La sesión se destruye al terminar la ejecución del Director, liberando los tensores del Context. El RunRecord sólo conserva metadatos del manifiesto; **Context todavía NO persiste tras cierre del proceso, no hay checkpoints ni scratch implementado**.
- Objetos modelo vivos (`MODEL`, `CLIP`, `VAE`, `CONTROL_NET`, `GUIDER`, `SAMPLER`, patchers) **no se deben guardar como referencia** en Context. Guardarlos haría imposible la frontera de memoria.
- No descargar modelos a ciegas: `/free` / `unload_all_models()`/nodos unload causaron caídas del proceso en Colab. `--cache-none` funcionó como variable de aislamiento en pruebas previas; **no demuestra liberación universal ni garantiza RAM completamente recuperada**.
- Dos barreras propuestas para el trabajo actual de memoria: **después de A** medir/recuperar; **antes de B** comprobar de nuevo, diagnosticar y sólo limpiar específicamente un propietario identificado cuando exista método seguro. *No implementadas como liberación total.*

## 3. Lo que YA existía y funcionó (antes del PR #6)

**Seis nodos V3 typed, se conservan sin modificación de IDs/esquema:**
- `WorkflowDirectorContextPutString` / `WorkflowDirectorContextGetString`
- `WorkflowDirectorContextPutImage` / `WorkflowDirectorContextGetImage`
- `WorkflowDirectorContextPutLatent` / `WorkflowDirectorContextGetLatent`

Pruebas **reportadas/observadas en Colab Free T4**:
- STRING A→B, IMAGE A→B, LATENT A→B, prueba de fallo y rechazo.
- Transferencia desde pestañas reales, recaptura y tab B ausente (fail-closed).
- Dos trabajos GGUF Klein Q4/Q6 ejecutaron **individualmente** con la configuración de prueba; **NO** se probó todavía transporte de LATENT pesado entre ellos.
- La observación `--cache-none` produjo valores cercanos a ~2.6–2.8 GiB RSS y uso bajo de VRAM (~0.18 GiB) después de trabajos de prueba, frente a ~8.7 GiB RSS con caché predeterminada en algunos ensayos anteriores. Son observaciones contextuales, **no** prueba de fuga ni compromiso de cifras fijas.
- ComfyUI v0.39.0, frontend 1.53.10; Colab Free T4; comando de ejecución con `--cache-none`.

Estos resultados previos NO deben atribuirse a los dos nodos universales del PR #6, que siguen **sin aceptación real**.

## 4. Lo que se implementó EN EL PR #6 (experimental, CI verde)

**Dos nodos adicionales**, dejando disponibles los seis anteriores:
- `WorkflowDirectorContextPutUniversal`: V3 `io.MatchType.Input` y `io.MatchType.Output` con misma template; un `key` STRING; `is_output_node=True` para forzar ejecución aun si no se conecta salida; `fingerprint_inputs=NaN` para evitar caché; `is_experimental=True`.
- `WorkflowDirectorContextGetUniversal`: salida V3 `io.AnyType.Output`, lee `read_any(job_id,key)`, clones independientes; `is_experimental=True`. Puede GET de entrada creada por el PUT universal o un PUT typed anterior, **pero un GET typed no acepta automáticamente un VALUE universal**.

**Nuevo `kind` interno `VALUE`** junto a STRING/IMAGE/LATENT; no representa el tipo semántico ComfyUI. El codec `workflowdirector/universal_codec.py` acepta por **estructura del objeto**, no por whitelist de nombres de sockets:
- `None`, `bool`, `int`, `float`, `str`, `bytes`, `bytearray`.
- `list`, `tuple`, `dict` con claves STRING, anidados hasta 32 niveles / máximo 10 000 componentes.
- Tensores PyTorch **de clase base exacta** `type(x) is torch.Tensor`, densos, strided, reales no sparse/quantized/meta; detached y copiados a CPU RAM (también copia si fuente ya estaba en CPU).
- CONDITIONING ordinario representado por listas/dicts/tensores, incluyendo embeddings y `pooled_output`.
- Valores estructurados de extensiones **sólo si** cumplen estas reglas; no hay todavía adaptadores de clases opacas.

Rechaza deliberadamente: objetos vivos de modelos, referencias GLIGEN/ControlNet/HookGroup que incluyan clases arbitrarias, ciclos, objetos Python desconocidos, tensor subclasses y transferencias que exceden los límites. **No usar `pickle` de objetos arbitrarios, no hacer deep-copy de un modelo, no conservar CUDA sin darse cuenta**.

**Presupuesto de datos lógico (no de pico RSS):** 128 MiB por entrada y 256 MiB agregado (committed+staged); el codec estima tamaño **antes** de transferir GPU→CPU y valida tamaño estimado = almacenado. Existe sobrecoste adicional por input original, GET clones, caché/allocator/metadata; no hay garantía real de pico RAM.

**Fixtures y casos de laboratorio en PR #6:**
- `nodes/conditioning_lab.py`: CONDITIONING fuente y sink que valida embeddings, `pooled_output`, metadatos, sentinel; fuente unsafe que contiene referencia opaca para prueba negativa.
- `workflows/universal_conditioning_A.json` y `workflows/universal_conditioning_B.json`: ejemplos visuales enlazados, NO abiertos todavía en frontend real.
- `scripts/acceptance_probe.py`:
  - `preflight`
  - typed previos: `string`, `image`, `latent`, `failure`
  - nuevos: `universal_image`, `universal_conditioning`, `universal_unsafe_conditioning`
- Tests: `tests/test_universal_context.py`, `tests/test_acceptance_plans.py`, `tests/test_universal_workflow_files.py`.
- Las negativas revisan **exactamente nodo que falló y fragmento de error esperado en el historial nativo**, no sólo cualquier error de A. El unsafe debe fallar A con `JOB_FAILED`, sin ejecutar B ni publicar manifiesto.
- La doble auditoría corrigió el rechazo de tensor subclasses antes de llamar métodos personalizados.

**NO afirmaciones de release:** `AnyType` es capacidad de cableado, **no validación automática del valor recuperado**; JSON válido y unit tests CI **no prueban** compatibilidad de la interfaz real ni transferencias T4.

## 5. Código a abrir en la próxima sesión sobre Context

- `__init__.py`: registro de nodos, incluyendo 6 typed + 2 universales + 3 fixtures CONDITIONING Lab.
- `nodes/context_nodes.py`: typed, `_job_id`, `_put`, `_get`, comportamiento Queue manual.
- `nodes/universal_context_nodes.py`: dos nodos públicos experimentales.
- `nodes/conditioning_lab.py`: lab source/sink y unsafe.
- `workflowdirector/context.py`: `ContextRegistry`, `StepPatch`, `ContextSession`, `read_any`, `VALID_TYPES`, validación de escritores, commits/rollback.
- `workflowdirector/context_codec.py`: dispatch typed/ VALUE, límites, CPU clones.
- `workflowdirector/universal_codec.py`: recursión segura.
- `workflowdirector/core/director.py`: secuencia de jobs, commit tras estado terminal, observaciones entre jobs.
- `workflowdirector/core/service.py`: exclusión de runs, cleanup de Context en `finally`.
- `workflowdirector/run_api.py`: validación del plan, escritores duplicados.
- `scripts/acceptance_probe.py`: aceptación real.
- `tests/test_universal_context.py`, `tests/test_acceptance_plans.py`, `tests/test_universal_workflow_files.py`.
- `web/` y componentes Lab: integración visual y captura de pestañas; consultar cambios reales antes de editar. **No modificar el frontend a ciegas.**

## 6. Diseño PENDIENTE y riesgos conocidos (priorizados PARA CUANDO SE REANUDE)

### P0 — Dependencia bloqueante: frontera de memoria del producto

**Trabajo ACTIVO AHORA, fuera de Context:** diagnosticar qué queda residente tras A y por qué; distinguir RSS/PSS/Pss_Anon/Pss_File, memoria de allocator y mmap GGUF, cachés, PyTorch CUDA allocated/reserved, NVML total y registro de modelos Comfy. Evitar `unload_all_models()` y rutas `/free`.

Herramientas examinadas: **ProfilerX** (por nodo/prompt_id, pero reinicia picos CUDA y parchea reset del ProgressRegistry), **Resource Snapshot** (AnyType passthrough; mide RAM global, requiere Python >=3.12), **Crystools**, `/proc/PID/smaps[_rollup]`, `comfy.model_management.current_loaded_models` con weakrefs/IDs de sólo lectura, **PyTorch CUDA Memory Snapshot**, `tracemalloc`, Memray (último recurso), Datadog (demasiado intrusivo al inicio). Leer **EXISTING_MEMORY_DIAGNOSTICS_RESEARCH**; *no instalar varias extensiones ni usar limpieza agresiva sobre el notebook validado*.

**Razón de posponer Context:** no diseñar expansión de tipos ni grandes copias de tensores sin entender primero sus consecuencias sobre RAM/VRAM y sin una barrera de memoria fiable. No perder avances.

### P1 — Semántica de tipos real entre A y B

Problema actual: `ContextManifest` identifica un PUT universal como `VALUE`; no registra el **tipo de socket original** (CONDITIONING, IMAGE, MASK, AUDIO, custom). Un GET con ANY se conecta a consumidores incompatibles; algunos tipos comparten Python `torch.Tensor`, por lo que ni siquiera el tipo Python basta. Un grafo A no puede inferir por `MatchType` el tipo de un socket en el grafo B independiente.

Necesario:
- Estudiar cómo extraer de forma confiable el tipo real declarado en la salida del productor en la compilación frontend/backend (schema V3, metadata de enlace) y cómo asociarlo a la clave escrita.
- Ampliar ContextEntry a metadatos tipo `key, original_socket_type, serializer/adapter_id, adapter_version, shape/dtype/device cuando aplique, origin_workflow/step, bytes, location, value` **sin exponer objetos vivos**.
- Validar antes de ejecutar B el contrato del consumidor (`class_type`, nombre de input/socket, tipo esperado) desde el prompt/schema; resolver comodines/casos dinámicos. Una conexión visualmente válida no certifica compatibilidad de ejecución.
- Compatibilidad de claves creadas con PUT typed y universales antiguos, migración de manifest, claves duplicadas y cambios de versión.
- Ensayo negativo IMAGE → MASK / CONDITIONING → incompatible, sin disparar un trabajo pesado.

### P1 — Memoria de transferencias y residencias

- Distinguir lo que ocupa Context de lo que mantiene Comfy/PyTorch externamente.
- Picos reales al clonar fuente→Context→B: no están acotados por 256 MiB de payload lógico.
- Escoger RAM frente a `/content` scratch, serialización CPU segura y durabilidad de checkpoints sin mantener model patchers; integridad de entrada/salida, ciclo de vida, limpieza de assets temporales.
- Presupuesto según presión real RAM libre, ventanas de consumo, número de consumidores, transferencia y costes de E/S.
- No introducir optimización si la memoria base y leaks no están caracterizados.

### P2 — Adaptadores extensibles para tipos de terceros

Diseñar SPI de codecs/serializers **registrables**, tipados y versionados, con un fallback seguro por estructura; advertencias útiles cuando un valor NO pueda trasladarse. No prometer compatibilidad total con clases opacas. Evitar `pickle` de objetos Python arbitrarios. Ejemplos: AUDIO, VIDEO, máscaras, conditioning con referencias externas, estructuras de custom nodes, objetos con handles no serializables. Algunos datos representan modelos y deben regenerarse, no conservarse.

### P2 — Persistencia y recuperación

- RunRecord persiste actualmente **sólo metadatos**, no el Context real.
- Scratch + durable assets en Drive, checkpoints, reanudación tras muerte del proceso y estado ambiguo de jobs.
- GET manual standalone actualmente no funciona, PUT manual es passthrough sin publicar; decidir contratos UX, fallback/checkpoints futuros.
- Orquestación N workflows existe en backend, el Lab UI todavía está limitado a A/B.

### P2 — Seguridad de orquestación

- Cancel/timeout no garantiza detener native job; tombstones evitan late-write, pero falta protocolo de cancelación/reconciliación.
- Queue exclusivity es observación no mutex atómico frente a clientes externos.
- Evitar asumir que B se puede ejecutar si no hay memoria suficiente, incluso con A terminado.
- No alterar el comportamiento de jobs nativos ni bloquear worker con nodos de orquestación.

## 7. Pruebas de aceptación CONTEXT (NO HACER AHORA; lista para cuando se retome)

Entorno obligatorio: **Colab Free / GPU NVIDIA T4 / RAM estándar / ComfyUI v0.39.0 + frontend 1.53.10 + `--cache-none`**, sin `/free`, sin unload forzado, sin A100/L4, sin instalar masivamente plugins.

Rama al evaluar el experimento:
```python
WD_REF = "feature/universal-context-nodes"
```
**No cambiar la rama del notebook de producción hasta decidir volver a Context y tener respaldo**. Tras instalar esa rama, reiniciar sólo el proceso de ComfyUI y verificar comandos/IDs.

Orden de pruebas:
1. `preflight`: IDs registrados, Comfy 0.39, Director listo, queue libre, proceso con `--cache-none`. Deben aparecer los 8 Context nodes y 3 fixtures Lab además de nodos nativos.
2. Repetir sin regresiones los casos typed `string`, `image`, `latent`, `failure` con 2 jobs distintos cuando corresponde.
3. `universal_image`: EmptyImage→PUT universal en A; GET universal→SaveImage en B; verificar salida/historial; añadir posteriormente comparación **exacta de píxeles**, no únicamente presencia de fichero.
4. `universal_conditioning`: A genera embeddings + pooled tensor + metadata; B verifica elemento a elemento y marca un sentinel en historial.
5. `universal_unsafe_conditioning`: A intenta publicar una referencia opaca; debe FALLAR por la causa prevista en PUT, **sin job B ni commit**.
6. Importar dos archivos `workflows/universal_conditioning_A.json` y `..._B.json` como pestañas Topbar, capturar desde Lab y ejecutar. Verificar cableado gráfico y recaptura, no sólo JSON.
7. CONDITIONING real de un text encoder/model workflow → PUT A, GET B → sampler compatible; probar que las referencias a modelos no quedan retenidas por Context.
8. Probar negativos de claves/tipos, links dinámicos, cancelaciones, variantes reales de LATENT, imágenes, VIDEO/AUDIO si se implementan adaptadores.
9. Finalmente Klein Q4→Q6 con transporte grande, medir **picos RAM/VRAM y liberación real** y repetir ciclos. No interpretar modelos reutilizados como prueba de descarga.

**CI verde NO sustituye estas pruebas.** Todos los pasos incluyen fecha, exacta versión, IDs nativos, logs, manifiesto y memoria.

## 8. Qué NO hacer si se abre otro chat

- No reimplementar desde cero Context ni borrar los seis typed de aceptación.
- No convertir todos los tipos a STRING / serializar `repr` como solución.
- No retener objetos `MODEL`/`CLIP`/`VAE`/`ControlNet` o `Tensor` CUDA por referencia para simular universalidad.
- No incorporar código GPL de KJNodes a un repo sin análisis/licencia ni confundir sus enlaces virtuales con transporte entre jobs.
- No llamar `/free`, `unload_all_models()`, HardDelete ni reiniciar el kernel como falso sustituto de una barrera estable.
- No proclamar validado el universal por CI ni declarar que la RAM residual es necesariamente fuga.
- No mover `main` ni `feature/colab-acceptance` ni cerrar/merge PR #6 sin petición explícita del usuario.
- No continuar Context hasta que el usuario lo vuelva a poner como prioridad.

## 9. Trabajo activo inmediato: memoria (para no perder el hilo al cambiar de chat)

**Cambio de prioridad acordado el 2026-10-08:** pausar desarrollo de Context y concentrarse en **identificar y gestionar RAM/VRAM**. Preguntas que hay que resolver: qué objetos/modelos/cachés/allocators permanecen tras trabajos independientes; si el residuo se estabiliza; qué liberar sin matar Comfy/Colab y cómo medirlo antes de B. Diseñar un experimento read-only en `--cache-none`, perfiles por nodo con ProfilerX **sólo si es compatible/aislado**, y snapshots por PID/NVML/PyTorch/model-registry. Muestra puntos: loader GGUF, Qwen/CLIP encode, sampler, VAE decode, Context PUT/GET (más adelante). Evitar instalar cuatro herramientas a la vez. Si los recursos no pueden liberarse dentro de un proceso, valorar arquitectura de aislamiento por proceso con Context serializado entre trabajos como opción posterior, no solución asumida.

Documento guía: `docs/EXISTING_MEMORY_DIAGNOSTICS_RESEARCH_2026-10-08.md`.

## 10. Texto para pegar al comenzar un chat nuevo

> Estamos desarrollando el repositorio `daneelolivaw2020/ComfyUI-WorkflowDirector`. Lee íntegramente `docs/HANDOFF_CONTEXT_PAUSADO_2026-10-08.md` en la rama `feature/universal-context-nodes` y sus documentos enlazados. Context universal está PAUSADO y preservado en el PR #6; NO lo reimplementes ni lo merges. Ya tenemos un baseline aceptado en `feature/colab-acceptance`. La prioridad actual es identificar qué retiene RAM/VRAM entre los workflows independientes en Colab Free T4 y preparar una barrera de memoria segura. Consulta también `docs/EXISTING_MEMORY_DIAGNOSTICS_RESEARCH_2026-10-08.md`. Trabaja sobre lo existente sin tocar la rama aceptada.

## 11. Criterio para poder reanudar Context

Cuando la estrategia de memoria esté caracterizada y el usuario vuelva a elegir Context:
- Recuperar estado del PR #6 y CI actual, comparar contra rama de base y releer auditorías.
- Corroborar contratos nativos API v0.39 en un runtime real, no sólo lectura de fuente.
- Priorizar **tipo/procedencia/validación cruzada** y **picos de memoria de CPU transport** antes de ampliar más tipos.
- Progresar en pequeños cambios reversibles, con tests y una prueba real T4 por capa.
- Registrar qué parte es **diseñada**, **implementada**, **unit-tested**, **runtime-proven** y **production-ready**.

**Este archivo es la congelación del trabajo de Context, no una declaración de finalización del producto.**
