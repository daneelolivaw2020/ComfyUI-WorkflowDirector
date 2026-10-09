# M-011 — Auditoría de los workflows reales «Luferra style» y notebook longtesting

**Fecha:** 2026-10-09. **Propósito:** preservar el hallazgo experimental del usuario y traducirlo a un diseño de frontera de memoria que conserve exclusivamente Context. **No se ha realizado ningún nuevo run ni se ha cambiado código de ComfyUI**.

## Material aportado

- `Luferra style - workflow A.json`, workflow frontend; 37 nodos y 50 enlaces, todos mode 0 (activos).
- `Luferra style - workflow B.json`, workflow frontend; 153 nodos y 153 enlaces, **77 mode 0** y **76 mode 4** (bypass/desactivados). Por ello **no** se puede afirmar que los 153 nodos se ejecutan.
- `base_8_oct_longtesting.ipynb`, 13 celdas; datos de configuración, no output de experimentos de RAM. La afirmación de mínima pérdida tras workloads complejos procede del usuario y NO debe transformarse en resultado cuantitativo no medido. La evidencia cuantitativa previa M-010 corresponde a seis jobs de los *otros* workflows, no necesariamente estos complejos.

**No copiar prompts, nombres personales de archivos de imagen ni credenciales del notebook al repositorio.** Se detectó **un token Civitai literal** en código fuente (celda «#7 - Download list»): recomendar ROTACIÓN del token y paso a secreto de Colab; no imprimir ni incluir valor.

## Características de A

Genera y posprocesa imagen con **Flux2 Klein 9B GGUF Q6_K** + encoder **Qwen3 8B Q6_K**, tipo CLIP `flux2`. Tres LoRA habilitadas (se omiten nombres irrelevantes al análisis de memoria). Pipeline de imagen con dos `LoadImage` referencia y resize CPU, dos nodos personalizados de acondicionamiento de imagen, sampler `SamplerCustomAdvanced` Euler/4 steps, VAE `flux2-vae.safetensors`, `DepthAnythingV2Preprocessor` y `OpticalRealism`. La salida de imagen va por:

`OpticalRealism [414]` → `MemoryStatus [419]` → `MemoryManager [422]` → `MemoryStatus [420]` → `RAMCleanup [423]` → `MemoryStatus [424]` → `SaveImage [415]` y `Image Comparer [416]`.

- `MemoryManager.widgets_values=[true,true,true,true,true]`, respectivamente `clean_gpu, clean_cpu, force_gc, reset_virtual_memory, restore_original_functions` según implementación pública actual de `ComfyUI-DistorchMemoryManager` (confirmar commit instalado).
- `RAMCleanup.widgets_values=[true,true,true,3]`, respectivamente `clean_file_cache, clean_processes, clean_dlls, retry_times` según `LAOGOU-666/Comfyui-Memory_Cleanup` (confirmar commit instalado).
- Los tres MemoryStatus están explícitamente enlazados en el trayecto del resultado. Incluso el `SaveImage` espera a `RAMCleanup` en A. **No se afirma que los datos de salida anteriores queden eliminados**: la imagen pasada debe mantenerse viva hasta guardarse; esto es compatible con la exigencia de Context.

## Características de B

Pipeline **Flux.1-dev GGUF Q4_K_S**, dual text encoder **T5 XXL GGUF Q4_K_S + CLIP-L safetensors**, VAE `ae.safetensors`; LoRA(s), control de imagen/canny, `PyraCannyPreprocessor`, `DepthAnythingV2Preprocessor`, componentes XLabs ControlNet, un sampler principal activo y otras ramas de sampler/VAE que están en **mode 4**. También utiliza **33 `GetNode` y 10 `SetNode` KJNodes** para conexiones virtuales internas del mismo workflow. **No son el Context transaccional entre trabajos de WorkflowDirector**. El grafo no tiene `WorkflowDirectorContextPut*` / `WorkflowDirectorContextGet*` ni los dos universales de PR #6.

Cadena activa observada:

`Text Overlay [63]` → `MemoryStatus [211]` → `MemoryManager [216]` → `MemoryStatus [212]` → `RAMCleanup [217]` → `MemoryStatus [214]` → `SaveImage [46]`.

Los dos nodos de limpieza tienen **parámetros idénticos a A**. **Importante:** hay al menos otra salida `SaveImage [20]` habilitada que recibe `Text Overlay [58]` **directamente**, por una rama distinta; no es downstream de `MemoryManager/RAMCleanup`. No afirmar que la limpieza se ejecutó tras *todas* las ramas activas o que el orden de todos los Output nodes queda garantizado por `node.order` de UI. Si se generaliza la solución, usar una frontera de memoria global post-job y no depender de un orden parcial entre branches.

## Notebook / entorno

- Notebook contiene 13 celdas; salida guardada de detección Python **3.13.15**, Torch **2.11.0+cu130**, Colab; descarga `ComfyUI v0.39.0` en la celda de instalación (pero `COMFY_VERSION=None` selecciona última estable al clonar un runtime nuevo: **no está fijada**).
- GGUF fijado a commit `6ea2651e7df66d7585f6ffee804b20e92fb38b8a`.
- WorkflowDirector instalado desde `feature/colab-acceptance`, salida guardada commit `62d43b1ddb16`; Context universal PR #6 **no está instalado ni aceptado**.
- ComfyUI arranque llama `--cache-none`, `--reserve-vram 0.8`; opt-in para ruta glibc preparado. Salida del notebook en esa celda indica **«ComfyUI ya está funcionando. Reconectando iframe»**: ese output no permite asegurar que esos flags se hayan aplicado a PID preexistente; los logs de M-010 sí muestran `Disabling intermediate node cache`.
- **Reproducibilidad pendiente:** `ComfyUI-DistorchMemoryManager` y `Comfyui-Memory_Cleanup` aparecen como URLs comentadas en la lista REPOS de instalación del notebook, no se clonan en una sesión fresca usando sólo esa celda. También `comfyui_controlnet_aux` aparece comentado aunque B contiene nodos de ese paquete. Deben declararse como dependencias efectivas, fijar commit y comprobar un entorno nuevo. `UPDATE_EXISTING=False` deja otros custom nodes dependientes del estado previo.
- La carpeta Google Drive `COMFYUI_STUFF` se copia sobre modelos y recursos ya instalados, sin evidencia de qué extensiones añade efectivamente; no adjudicar la instalación de memory nodes a esa celda.

## Código de las limpiezas existentes (revisión de implementación pública)

- `ussoewwin/ComfyUI-DistorchMemoryManager/memory_manager.py` `MemoryManager`: `gc.collect`, `torch.cuda.empty_cache`, `torch.cuda.synchronize` y, con `reset_virtual_memory=true`, `comfy.model_management.free_memory(1e30, torch.device(cuda))`; puede ser **unload** de modelos. La opción `restore_original_functions` sólo hace import y muestra texto en código consultado (no restaura realmente monkey patches).
- `LAOGOU-666/Comfyui-Memory_Cleanup/__init__.py` `RAMCleanup`: en Linux, con `clean_file_cache=true`, llama `ctypes.CDLL('libc.so.6').malloc_trim(0)` cada iteración; con `retry_times=3` realiza **hasta 3 intentos y 3 sleeps de 1 segundo**. Los flags `clean_processes` y `clean_dlls` de esa implementación sólo afectan Windows y no limpian procesos externos en Linux. El nombre del checkbox `clean_file_cache` es engañoso: `malloc_trim` **no** purga Linux page cache global.
- Son mecanismos nativos potencialmente invasivos. El usuario constató **seis ejecuciones previas completas** y baja memoria residual para su secuencia concreta M-010; no equiparar a garantía universal ni asumir el mismo éxito con los dos workflows complejos sin métricas compartidas.

## Conclusiones y acciones correctas

1. **Logro práctico reproducible que merece ser preservado:** el usuario armó una secuencia in-graph `MemoryManager → malloc_trim-backed RAMCleanup` con estados antes/intermedios/después, y observó poca pérdida de RAM en workloads complejos (cualitativo). Es la **candidata primera** para barrera del mismo PID, antes de plantear restart por procesos.
2. **Lo que falta para cumplir producto:** los workflows **NO transfieren aún datos mediante PUT/GET de WorkflowDirector**; sin Context real no hay prueba de conservación de valores y liberación del resto. La frontera objetivo sigue siendo `A completed → Context committed → cleanup of non-Context refs → baseline+Context → B`. La implementación de limpieza incrustada puede hacer cleanup *antes* de la confirmación del Job; debe auditarse para garantizar orden y rollback.
3. En A la limpieza está en la cadena hacia todos los outputs relevantes, de forma que **ocurre antes del SaveImage**, no necesariamente después del trabajo terminal. En B hay otra rama de SaveImage fuera de la cadena, por lo que no existe una barrera global fiable impuesta por el grafo.
4. La mejor integración técnica probable es ofrecer un preset de limpieza opt-in en el orquestador en una etapa post-terminal/post-commit, auditado para compatibilidad con las llamadas probadas y con tiempos/errores bien definidos; no clonar arbitrariamente código o añadir otro nodo público de limpieza. **Aún no implementado.**
5. Tratar `MemoryManager` y `RAMCleanup` como candidatos que funcionan en este ambiente **sin prometer 100% liberación ni seguridad genérica**. El nivel de referencia aceptable se compara con Comfy en frío + tamaño real Context, no contra 0 ni solo contra memoria disponible global.
6. Preservar JSON originales y notebook, **sin publicarlos** en GitHub por contenido de prompts, rutas de imágenes y credencial literal. PR #6 Context universal permanece pausada y no se modifica.

