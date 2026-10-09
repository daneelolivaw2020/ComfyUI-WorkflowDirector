# Colab Runbook — Diagnóstico read-only de memoria WorkflowDirector
**Fecha**: 2026-10-08. Usar junto con [MEMORY_WORKSTREAM_2026-10-08.md](MEMORY_WORKSTREAM_2026-10-08.md).
**Objetivo:** establecer línea base real y localizar por nodo dónde aparece la retención, sin cambiar Torch/CUDA ni ejecutar unload.

## Antes de empezar: condiciones y parada segura
- Google Colab Free/T4/RAM estándar. El usuario reportó **Python 3.13.15, torch 2.11.0+cu130, CUDA de Torch 13.0**.
- Verificar Comfy 0.39.0, frontend 1.53.10, arranque `--cache-none`, `port=8188`; no asumir que todas las sesiones mantienen las mismas versiones.
- **No tocar** `feature/colab-acceptance` en el custom node en uso, el PR de Context universal #6, los workflows Klein conocidos, ni la celda de instalación de Torch. Deshabilitar Auto Queue.
- **No instalar ningún nodo de unload** ni llamar `/free`, `unload_all_models()`, `gc.collect()` durante las medidas. No hacer restart del kernel para «arreglar» una fuga: invalidaría la observación.
- Para una corrida comparable, no cambiar modelo, prompt, semilla, LoRA, resolución, sampler, flags ni otras extensiones entre la línea base y la medida con profiler.
- Archivos bajo `/content` son **efímeros**. Copiarlos al Drive o descargar manualmente cuando se quiera conservar una sesión; aquí sólo el código/documentos quedan en GitHub.

## D0. Verificación de estado SIN instalaciones

**Celda Colab:**

```python
import sys, json, urllib.request, subprocess
from importlib.metadata import version
print("Python:", sys.version.split()[0])
print("Torch instalado (sin importarlo):", version("torch"))
# Do NOT call torch.cuda from notebook: it can create another CUDA context.
query = subprocess.run(
    ["nvidia-smi", "--query-gpu=name,driver_version,memory.used,memory.total",
     "--format=csv,noheader,nounits"],
    text=True, capture_output=True, check=False,
)
print("NVIDIA (uso GLOBAL, no exclusivo Comfy):", query.stdout.strip())
url = "http://127.0.0.1:8188/workflowdirector/health"
with urllib.request.urlopen(url, timeout=10) as r:
    health = json.load(r)
print("Health:", json.dumps(health, ensure_ascii=False, indent=2)[:3000])
```

**Nota:** esta celda evita `import torch` deliberadamente para no crear un segundo contexto CUDA desde el notebook. Si celdas anteriores **ya** importaron Torch o accedieron a CUDA, documentarlo: la medición global de nvidia-smi también puede incluir ese contexto adicional. No sirve medir `torch.cuda.memory_allocated()` del notebook para conocer el allocator del **proceso ComfyUI**, que es otro PID. Leer memoria del Comfy desde su servicio y `/proc`. Ejecutar D0 después de que Comfy esté arrancado. Si `/workflowdirector/health` falla, no instalar ProfilerX hasta resolver el arranque base.

## D1. Línea base SIN extensiones de memoria

**Celda para obtener el observador separado** (NO instalarlo como custom node en Comfy):

```python
from pathlib import Path
import subprocess, sys

MEM_TOOLS = Path("/content/WorkflowDirector-Memory-Audit")
if not (MEM_TOOLS / "scripts" / "memory_watch.py").exists():
    subprocess.run([
        "git", "clone", "--branch", "feature/memory-diagnostics",
        "--single-branch",
        "https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector.git",
        str(MEM_TOOLS),
    ], check=True)
print("Audit tool commit:",
      subprocess.check_output(["git", "-C", str(MEM_TOOLS),
                               "rev-parse", "HEAD"], text=True).strip())
```

**Celda para iniciar el observador mientras Comfy está vivo:**

```python
import subprocess, sys, time
from pathlib import Path

WATCH_FILE = Path("/content/workflowdirector_memory_watch.jsonl")
WATCH_STDOUT = Path("/content/workflowdirector_memory_watch.log")
# Elegir nombres nuevos si se repite una sesión: JSONL se escribe en append.
WATCH_LOG_HANDLE = WATCH_STDOUT.open("a", encoding="utf-8")
WATCH_PROC = subprocess.Popen([
    sys.executable, str(MEM_TOOLS / "scripts" / "memory_watch.py"),
    "--port", "8188",
    "--duration", "1200",
    "--interval", "2",
    "--output", str(WATCH_FILE),
], stdout=WATCH_LOG_HANDLE, stderr=subprocess.STDOUT)
time.sleep(3)
if WATCH_PROC.poll() is not None:
    WATCH_LOG_HANDLE.close()
    raise RuntimeError(WATCH_STDOUT.read_text()[-5000:])
print("Observador activo, PID externo:", WATCH_PROC.pid)
print("Archivo:", WATCH_FILE)
```

A continuación, **desde la UI de Comfy/WorkflowDirector**, ejecutar **un trabajo trivial** primero y, sólo si funciona, nuestro A Klein Q4, medir frontera POST_A y A→B con Q6 en los mismos parámetros conocidos. NO iniciar dos trabajos a la vez. Copiar IDs `prompt_id` / run_id, tiempos y estados. Hacer una pausa de observación entre A y B sin inventar que ese tiempo fuerza GC.

**Celda para detener el observador al terminar:**

```python
if WATCH_PROC.poll() is None:
    WATCH_PROC.terminate()
    WATCH_PROC.wait(timeout=10)
WATCH_LOG_HANDLE.close()
print("JSONL:", WATCH_FILE, "bytes:", WATCH_FILE.stat().st_size)
print("LOG:", WATCH_STDOUT)
```

Si el notebook pierde la variable `WATCH_PROC`, no ejecutar `killall python`; localizar el proceso concreto con `ps`. El script se detiene solo por duración o Ctrl-C. Si Comfy se termina, el observador se detiene con error para no monitorizar un PID reutilizado.

**Qué sale del JSONL:** línea por muestra con `utc`, `comfy_pid`, `process.rss_bytes/pss_bytes/pss_anon_bytes/pss_file_bytes` cuando el kernel los expone, y `gpu_global[].used_bytes/total_bytes` por nvidia-smi. RAM es del PID Comfy; GPU nvidia-smi es uso global GPU, no exclusivo del proceso. Correlacionar con Jobs/RunRecord. No comparar directamente este RSS con la RAM global de Resource Snapshot.

## D2. ProfilerX — instalar SOLO DESPUÉS del baseline

**Custom node a instalar:** `ComfyUI_ProfilerX` de `ryanontheinside`.
- Pin auditado: `007bc3439b4f73c2e60099812d0c371b7e97d2c8`.
- Declara Python >=3.8, `psutil>=5.9`. Tu Python 3.13 satisface el requisito declarado; Comfy 0.39/Torch 2.11 debe verificarse en runtime.
- **No hay nodos nuevos que insertar**: funciona como monitor automático y añade botón de perfilado en la UI.
- Antes de instalar: detener o dejar acabar los jobs y el monitor externo D1; anotar su fichero JSONL.

**Celda de instalación en la ruta del Comfy vivo:**

```python
from pathlib import Path
import subprocess, sys
import psutil

COMFY_DIR = Path("/content/ComfyUI")  # AJUSTAR si el notebook usa otra ruta
assert (COMFY_DIR / "main.py").is_file(), "Revisar ruta real de ComfyUI"
PLUGIN_DIR = COMFY_DIR / "custom_nodes" / "ComfyUI_ProfilerX"
PIN = "007bc3439b4f73c2e60099812d0c371b7e97d2c8"

if not PLUGIN_DIR.exists():
    subprocess.run([
        "git", "clone",
        "https://github.com/ryanontheinside/ComfyUI_ProfilerX.git",
        str(PLUGIN_DIR),
    ], check=True)
assert (PLUGIN_DIR / ".git").is_dir(), "Ya hay una carpeta no-Git con ese nombre"
subprocess.run(["git", "-C", str(PLUGIN_DIR), "checkout", "--detach", PIN],
               check=True)
print("ProfilerX:", subprocess.check_output([
    "git", "-C", str(PLUGIN_DIR), "rev-parse", "HEAD"
], text=True).strip())
print("psutil disponible:", psutil.__version__)
print("SIN cambios a torch/CUDA ni nuevas dependencias")
```

Si `import psutil` falla, **no instalar `torch`**; comprobar la instalación/entorno Python de Comfy y usar únicamente `python -m pip install 'psutil>=5.9.0'` con el intérprete exacto que lo ejecuta. En la instalación normal Comfy, `psutil` ya está presente.

**Reiniciar SOLO el proceso ComfyUI** usando la misma celda de arranque del notebook, manteniendo `--cache-none` y puerto 8188; **no reiniciar todo Colab**, no borrar modelos ni cachés manualmente. Al arrancar, comprobar logs de import de ProfilerX. UI: botón con icono de gráfica.

**Celda de verificación, SIN trabajo activo:**
```python
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8188/profilerx/stats",
                            timeout=10) as r:
    result = json.load(r)
print("ProfilerX endpoint OK:", sorted(result.keys()))
```

**IMPORTANTE:** no pedir `/profilerx/stats` mientras un job corre: su implementación invoca `handler.flush()`. Hacer un workflow pequeño para asegurar estabilidad; luego Klein Q4 y Q6 siguiendo **exactamente** la comparación D1. Al terminar cada job, exportar o guardar JSON de la respuesta de `GET /profilerx/stats`. Correlacionar `promptId`, `nodeId`, `nodeType` con Jobs. ProfilerX modifica/reset la estadística global de pico CUDA por nodo; **no interpretar esos picos como compatibles directamente con otras mediciones globales**.

**Rollback si falla import o comportamiento:** parar sólo ComfyUI; mover carpeta `ComfyUI_ProfilerX` FUERA de `custom_nodes` (por ejemplo a `/content/ComfyUI_ProfilerX_DISABLED`) y reiniciar ComfyUI con flags anteriores. No eliminar 723 paquetes ni reinstalar Torch/CUDA.

## D3. NO instalar todavía Resource Snapshot

**Opción futura**: `PBandDev/comfyui-resource-monitor`, nodo exacto en `PBandDev/Resource Monitor → Resource Snapshot`. Python declarado >=3.12 y usuario tiene 3.13.15. Instalar sólo en segunda corrida si precisamos datos en puntos manuales. Su `ram_used_bytes` es del sistema, y `vram_used_bytes` es global GPU. No confundir sus valores con RSS de Comfy o Torch allocated.

Si se instala posteriormente, en Settings → `Resource Monitor`, **desactivar `Show Clear Buttons`**. Nunca pulsar `Unload Models` ni `Free Memory`. No instalarlo junto con ProfilerX para el primer experimento.

## Qué datos traer al siguiente chat

- Los resultados de D0 completos; rutas Comfy y flags de arranque.
- Capturas o JSON de ProfilerX y mensajes de error import si ocurren.
- `/content/workflowdirector_memory_watch.jsonl`, o sus muestras relevantes inicio A / final A / pre B / fin B.
- IDs de jobs y estado terminal; título o nombres de nodos con mayor delta.
- Si RAM residual crece continuamente o queda estable (no etiquetar fuga sin series repetidas).

## Formato sugerido de reporte

```text
EXPERIMENTO: M0 baseline | M1 ProfilerX
COMFY: 0.39.0 / frontend 1.53.10 | Py: 3.13.15
TORCH: 2.11.0+cu130 | CUDA: 13.0 | GPU: T4
FLAGS: --cache-none | Director rama y SHA:
ProfilerX SHA (si aplica):
Workflows/semillas: A=... B=...
Job IDs: A=... B=...
BASELINE (PSS/RSS/VRAM):
POST_A immediate:
POST_A stable:
PRE_B:
POST_B:
Resultados/errores:
JSONL / ProfilerX history:
Conclusión: confirmado / descartado / inconcluso
Siguiente prueba y qué hipótesis discrimina:
```

## Archivo persistente y continuidad
Código y docs en rama `feature/memory-diagnostics`, PR de memoria separado por abrir. PR #6 Context universal permanece congelado. En un nuevo chat leer `docs/MEMORY_WORKSTREAM_2026-10-08.md` y este runbook antes de ejecutar cambios.
