# Context universal — reanudación en laboratorio (2026-10-09)

**Autoridad:** el usuario decidió explícitamente retomar PR #6, tras observar experimentalmente que los nodos existentes de gestión de memoria funcionan repetidamente dentro de sus workflows. Esta nota reanuda la prioridad de **Context**, dejando la limpieza como proyecto paralelo; el handoff del 2026-10-08 permanece íntegro como histórico.

## Resultado de esta iteración

- **Lab UI:** botón **Run B only** incorporado. Usa la MISMA `startRun([state.B])` que A-only/A→B; el backend soporta RunPlan de un paso y conserva validación de pestaña, actualización fresca y bloqueo ante ejecución incierta. Los tres botones visibles son `Run A only`, `Run B only`, `Run A → B`.
- **Límite inalterado:** `Run B only` **NO reutiliza Context de un run A previo**. Actualmente `ContextRegistry` es run-scoped y `DirectorRunService` hace `end_run()` en `finally`. Si B necesita un GET que escribió A, sólo ejecutar `Run A → B`; B solo debe fallar explícitamente si el Context no existe. Para continuidad inter-run habría que introducir checkpoint/restauración, diferente alcance.
- **Universal V3 ya existía en PR #6:** `WorkflowDirectorContextPutUniversal` usa `io.MatchType.Template` común en Input/Output; `WorkflowDirectorContextGetUniversal` usa `io.AnyType.Output`. Estos son los **dos nodos públicos universales** a probar. Se mantienen sin cambio los 6 nodos typed anteriores y su suite.
- **Nuevos ejemplos VISUALES de 2 nodos cada uno**: `workflows/universal_image_A.json` (EmptyImage de 96×64→PUT key `demo.image`) y `workflows/universal_image_B.json` (GET key `demo.image`→SaveImage). Ejemplos ya existentes `universal_conditioning_A.json` y `_B.json`: transferir CONDITIONING normal con embeddings, pooled_output y metadatos verificados por sink.
- Agregados tests `tests/lab_ui.test.cjs` para B only envío único, snapshot fresco, tab faltante, label visible y advertencia, y `tests/test_universal_workflow_files.py` para grafo IMAGE y sockets `COMFY_MATCHTYPE_V3`/`*`. **CI y pruebas reales deben verificarse; ningún cambio por sí solo prueba ejecución real de Comfy.**
- Baseline aceptado `feature/colab-acceptance` / commit `62d43b1` sin cambios. PR #6 continúa DRAFT; no merge.

## Ejecución manual más sencilla — no cargar modelos y no instalar herramientas extra

1. En notebook de Colab, respaldar datos de sesión y fijar temporalmente `WD_REF = "feature/universal-context-nodes"` en la celda selectora; instalar/actualizar únicamente WorkflowDirector en `/content/ComfyUI/custom_nodes/ComfyUI-WorkflowDirector`. **Reiniciar solamente proceso ComfyUI** (nuevos nodos V3 + frontend no se registran con `importlib.reload`); no reiniciar kernel, no forzar memoria ni poner nodos unload en la prueba Context inicial.
2. Confirmar `/workflowdirector/health` ready, `--cache-none`, cola vacía; verificar que Comfy ha registrado IDs `WorkflowDirectorContextPutUniversal`, `WorkflowDirectorContextGetUniversal` y los fixtures de CONDITIONING.
3. Configurar pestañas Topbar; abrir como dos pestañas independientes `workflows/universal_image_A.json` y `..._B.json`. Verificar visualmente que el cable `IMAGE → MatchType` y `AnyType → IMAGE` es aceptado sin perder tipos ni remapear nombres. Capture current as A, Capture current as B. Pulsar **Run A → B**, no B-only para GET.
4. Confirmar job A `completed`, Context `demo.image` en manifiesto (kind `VALUE`) y job B `completed`, `SaveImage` output con prefijo `WD_Universal_Context_Image`. Esto valida flujo básico, **no todavía igualdad de píxeles ni compatibilidad ANY general**. Recapturar tras cambio de tab y repetir para corroborar que no se usa snapshot obsoleto.
5. Repetir par `workflows/universal_conditioning_A.json` / B: sink debe mostrar `PASS_CONDITIONING_TRANSFER_VISUAL_CONDITIONING_SENTINEL`; comprueba tensors/pooled/metadatos.
6. Ejecutar prueba negativa `universal_unsafe_conditioning` desde `scripts/acceptance_probe.py`: debe fallar A en PUT por tipo opaco exacto y no iniciar B. Comprobar backend y registro nativo.
7. Solo después ampliar a STRING/INT/LATENT, objetos de extensión simples, comprobar metadatos de socket y rechazos por tipo; tipos opacos necesitan adaptadores versionados, no basta AnyType para retener objetos vivo de modelo.

## Sobre cleanup al inicio

En el grafo Comfy, el orden visual de nodos o `node.order` **no es una barrera de ejecución fiable**. Para garantizar limpieza **antes de carga de modelos** se necesita dependencia causal de TODAS las ramas (incluidos loaders sin entrada), o una **etapa nativa de limpieza separada antes del workflow** programada por Director, con cola exclusiva y resultado terminal. Ésta es una función posterior; NO se ha implementado en este PR. Integrar un cleanup post-job/presiguiente sólo cuando Context commit y las salidas previas estén seguros, con verificación y rollback. El usuario observó que su combinación de MemoryManager y RAMCleanup funciona en sus workflows complejos, pero no hay que convertirla en descarga global ciega en la rama Context.

## Requisito central preservado

Context explícito debe ser el **único payload** sobreviviente de un workflow previo, además del suelo inevitable de ComfyUI/Python/CUDA. La ruta visual universal es solo primer escalón funcional; limpieza y retorno a baseline + Context forman el gate final, aún no aprobado.

## Resultado observado: tipo de socket personalizado — 2026-10-09

**Evidencia compartida por usuario, ejecución real en ComfyUI / Colab; sin historial nativo íntegro adjunto.**

- Workflow A: `workflows/universal_unknown_socket_A.json`, document UUID `17233cf4-d372-48ce-9b66-36109970ad0c`.
- Workflow B: `workflows/universal_unknown_socket_B.json`, document UUID `14211576-04d3-4b09-87b4-f46e5d86337d`.
- Run UUID: `37d8e656-249a-45b0-8ef3-eaf7d9671d21`.
- Reportado por panel: **phase completed**; Context `demo.mystery | VALUE | 142 bytes`.
- Socket de A/B: `WD_MYSTERY_BUNDLE_V1`, deliberadamente desconocido para los nodos PUT/GET y el codec universal; `io.Custom` solo aparece en nodos de prueba `nodes/unknown_socket_lab.py`.
- Contenido generado: `dict` con etiqueta, `torch.Tensor`, diccionario anidado, lista y tupla. El consumidor B (`WorkflowDirectorTestMysterySink`) es `is_output_node=True` y falla si cambian esos datos; la finalización exitosa con este workflow indica que el verificador terminó sin lanzar excepción.
- **Aprobado funcionalmente:** empalme V3 `MatchType`/`AnyType` y transporte seguro de **estructura ordinaria tras un nombre de socket personalizado desconocido** entre jobs nativos independientes.
- **No demostrado:** clonación de instancias Python opacas arbitrarias, tipos dinámicos de extensiones reales, identidad semántica de socket persistida en Context, durabilidad entre runs, memoria near-cold. `142 bytes` es tamaño lógico estimado del payload (no pico RSS/VRAM).
- **Preferencia expresa del usuario:** para esta etapa **él asume la compatibilidad entre los sockets de A/B**; si conecta datos incompatibles, se acepta que B falle. No priorizar una capa automática de rechazo por nombre de socket antes de experimentar con tipos reales. Sí conservar la negativa segura a referencias de modelos u objetos opacos que impidan la liberación de memoria.

Pruebas previas compartidas verbalmente:
- Universal IMAGE: A/B jobs success, PreviewImage generó 1 imagen en historial y SaveImage produjo archivo; nodos visuales PreviewImage / GetImageSize no mostraron los resultados esperados en la pestaña B (incidencia frontend separada, sin diagnóstico cerrado).
- Universal CONDITIONING: `Run 3caa60f9-2649-4ee1-9132-39f5bcc993d8`, `phase completed`, Context `demo.conditioning | VALUE | 135 bytes`, con sink verificando embeddings/pooled/metadatos.

**Siguiente prueba de mayor valor:** transferir un socket personalizado *real* de una extensión instalada cuyo contenido sea una estructura copiable, usando los mismos PUT/GET; y una prueba negativa con objeto opaco para confirmar rechazo seguro (sin intentar preservar modelos vivos).
