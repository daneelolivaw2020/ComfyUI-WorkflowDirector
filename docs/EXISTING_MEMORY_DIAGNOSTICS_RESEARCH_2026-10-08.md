# Existing ComfyUI and Python memory diagnostics — research for WorkflowDirector
Date: 2026-10-08
Status: research only; **no monitoring plugin installed** in validated Colab

## Why this is needed

Our primary objective is a strong memory boundary: after A completes, only
committed Context values should be intentionally retained for B, along with the
irreducible ComfyUI/Python/CUDA runtime baseline. We must distinguish *retained
objects* from *reusable allocator memory* and *file-backed mappings* before
adding any cleanup. Existing --cache-none real T4 tests showed low post-job
VRAM and ~2.6-2.8 GiB process RSS, not proof of a leak.

No extension is currently proven compatible with our exact ComfyUI v0.39.0 /
frontend v1.53.10 / Colab Free T4 installed environment.

## Candidates evaluated from upstream code

| Candidate | Useful for | Code-level caveat | Recommendation |
|---|---|---|---|
| [ProfilerX](https://github.com/ryanontheinside/ComfyUI_ProfilerX) | Automatic per-node before/after RAM RSS and PyTorch CUDA allocation, peak allocated VRAM, promptId/nodeId/nodeType, timing/cache; GET /profilerx/stats | v2 uses Comfy ProgressHandler but patches reset_progress_state; calls torch.cuda.reset_peak_memory_stats() on each node (conflicts with other global peak accounting). Reported RAM 'peak' comes from endpoint RSS, not continuous sample peak. Profiling may flush run state when endpoint is called mid-job. Old prestartup.py from legacy implementation still exists and should not be enabled. | **Candidate #1** in isolated test environment, only one profiler enabled, query stats after native job terminal. |
| [Resource Snapshot](https://github.com/PBandDev/comfyui-resource-monitor) | Per-graph snapshots with AnyType passthrough and NVML GPU totals | pyproject requires Python >=3.12 (check actual Colab). RAM is psutil.virtual_memory (system-wide, NOT Comfy process RSS); NVML is GPU-wide. Built-in Unload Models / Free Memory controls dangerous for our past crashing case. AGPL-3.0: do not copy source into own repo. | Optional only after environment compatibility check; hide/avoid all cleanup controls. |
| [Crystools](https://github.com/crystian/ComfyUI-Crystools) | UI telemetry; Stats system for LATENT pipe | Mostly dashboards/system stats, not per-node object ownership. A lot of unrelated nodes/dependencies. | Lower priority than ProfilerX. |
| [Crystools MonitorOnly](https://github.com/BobRandomNumber/ComfyUI-Crystools-MonitorOnly) | Lightweight Nvidia UI only | No in-graph nodes or allocation attribution. | Optional visual feedback. |
| [ComfyUI MemoryManagement](https://github.com/kaaskoek232/ComfyUI-MemoryManagement) | Leak-detection node uses tracemalloc deltas | tracemalloc tracks Python allocations and misses many native Tensor/GGUF buffers; same package includes aggressive `unload_all_models()` and auto cleanup. | Do NOT install as initial observer on T4. |
| [comfyui-memory-tools](https://github.com/rghvdberg/comfyui-memory-tools) | Manual/graph unload buttons | Intentionally unloads models/cache, exactly the prior unsafe experiment class. | Not a diagnostic-first tool. |
| [Comfy-Org Datadog Monitor](https://github.com/Comfy-Org/comfyui-datadog-monitor) | Workflow/promptId/nodeId traces, optional detailed CUDA history | Requires ddtrace/agent, monkey-patches native execute_async/execute, automatic instrumentation. Risk/complexity unacceptable for first Colab tests. | Architectural reference, not initial install. |
| [PyTorch CUDA snapshot](https://docs.pytorch.org/docs/stable/torch_cuda_memory.html) | Allocator block addresses, stack traces, active tensor allocations, VRAM events; optional pinned host memory | PyTorch allocator only; native/CUDA direct allocations not visible. Trace buffers grow without a bounded max_entries; pickled snapshots should not be unpickled from untrusted sources. | Second-stage bounded targeted capture only if VRAM residual issue. |
| [Bloomberg Memray](https://bloomberg.github.io/memray/attach.html) | Python + native CPU allocations; stack attribution | Attaching injects code into live PID and can deadlock/crash; ptrace restrictions may block it. | Last resort in expendable process. |
| Linux /proc/PID/smaps_rollup | RSS/PSS, Pss_Anon/File/Shmem for exact Comfy PID | System metrics, not ownership. File-backed mappings can show GGUF pages without implying a leak. | **Immediate safe read-only instrumentation**. |
| Comfy model_management.current_loaded_models | Current LoadedModel/Patcher registry, weakref identity/type/estimated size | Must read only; inspect weakrefs without keeping model objects alive; registry != all Python references; loaded != GPU resident. | **Immediate safe read-only instrumentation** after auditing exact v0.39 behavior. |

## Discovery facts supported by upstream source

1. Comfy v0.39.0 `comfy/model_management.py` has
   `current_loaded_models` and `LoadedModel._model = weakref.ref(model)`,
   plus `loaded_models(only_currently_used=False)` and
   `cleanup_models_gc()`. We can snapshot **only metadata**, including
   `id(model)`, `type`, loaded_size, offloaded size, without serializing
   models or calling unload APIs.
2. ProfilerX v2 `handler.py` uses official `ProgressHandler`
   `start_handler/finish_handler`, whose tagged Comfy v0.39.0
   `comfy_execution/progress.py` supports registry registration.
   ProfilerX `__init__.py` still monkey-patches reset of that registry;
   extension's README 'no monkey-patching' is overly broad. Its legacy
   `prestartup.py` has invasive monkey-patches; DO NOT enable it.
3. ProfilerX `metrics.py` sets
   `totalRamPeak = psutil.Process(...).memory_info().rss` at read time:
   this is **not a sampled in-node RAM peak**. It calls
   `torch.cuda.reset_peak_memory_stats()` per node, which changes the
   allocator-global peak statistics seen by other observers.
4. Resource Snapshot `nodes.py` provides
   `io.AnyType.Input/Output('passthrough')`; `collector.py` samples
   `psutil.virtual_memory()` (system), NVML used/total (GPU global).
5. `tracemalloc` measures Python allocator blocks; it cannot be used as a
   complete answer to GGUF memory-mapped model buffers / C++ tensor backing.
6. PyTorch documents that `memory_allocated()` < NVML GPU used is normal,
   due to caches and CUDA context, and PyTorch snapshot misses allocations
   outside the PyTorch CUDA allocator.

## Lab protocol, non-destructive

**Never install multiple profilers at once**, and never put unload nodes in
our known-good Klein graphs. Keep `--cache-none` constant and preserve the
baseline acceptance branch and Colab notebook.

1. Record baseline with no additional extensions:
   Comfy PID RSS/PSS/Pss_Anon/Pss_File, cgroup RAM, Torch allocated/reserved
   GPU, NVML used/free GPU, Context bytes, registry of loaded model identifiers
   (metadata only). Run repeated **A-only** and then A→B Q4/Q6 cycles, at
   baseline, after native completed, end of post-job observation and pre-B.
   A stable 2.6-2.8 GiB resident process is not by itself a leak.
2. In an *isolated diagnostic environment* install only pinned ProfilerX v2
   if its 0.39 compatibility is validated first. Disable all automatic
   memory cleanup. Run exact same workloads; collect /profilerx/stats only
   after each native terminal completion, matched to the recorded promptId.
   Compare node IDs/type and per-node **before/after deltas** at: GGUF loader,
   Qwen/CLIP encode, sampling, VAE decode, SaveImage, Context PUT/GET.
   Loader nodes may create handles while actual GPU load happens later.
   Do not confuse node timing with allocator ownership.
3. If point measurements are insufficient, use a read-only out-of-process
   periodic sampler (short, bounded interval) of PID RSS and smaps_rollup,
   NVML/cgroup. This catches transient RAM peaks missed by ProfilerX.
4. Classify residuals:
   - Pss_File grows: inspect mapping paths and GGUF mmap; not necessarily leak.
   - Pss_Anon grows: CPU tensor/native/Python allocator; inspect cache and
     model weakrefs; if justified, Python tracemalloc or controlled Memray.
   - Torch CUDA allocated grows: live tensors; use bounded
     torch.cuda.memory._record_memory_history and memory_viz on a diagnosis run.
   - Torch CUDA reserved grows with allocated stable: allocator pool cache.
   - NVML GPU used grows without Torch allocated/reserved growth: external CUDA
     allocators, pinned/native contexts; CUDA snapshot alone is insufficient.
5. Only after measurements distinguish causes, design *two read-only
   checkpoints* (post-A and pre-B). Controlled cleanup, if necessary, must
   target a known owner and be proven safe; repeating a blanket unload is NOT
   an acceptable second pass.
6. Verify with no instrumentation that any remediation genuinely reduces
   residual memory and allows B to complete. Every change must keep previous
   Context commit/failure and A→B acceptance tests green.

## Proposed per-event telemetry record

`run_id, step_id, job_id/prompt_id, node_id, class_type, timestamp,
 phase, rss, pss, pss_anon, pss_file, cgroup_available,
 torch_cuda_allocated, torch_cuda_reserved, nvml_gpu_used,
 nvml_gpu_free, context_committed_bytes, live_model_metadata_ids`.

Never retain `torch.Tensor`, ModelPatcher, CLIP, VAE, ControlNet or actual
conditioning objects in the profiler record. Only small plain metadata/IDs.
The same model ID across phases is a clue, **not** standalone proof of a
retained allocation or leak.

## Links
- Comfy v0.39 tagged source:
  https://github.com/Comfy-Org/ComfyUI/blob/v0.39.0/comfy/model_management.py
  https://github.com/Comfy-Org/ComfyUI/blob/v0.39.0/comfy_execution/progress.py
- Linux kernel smaps_rollup:
  https://www.kernel.org/doc/html/latest/filesystems/proc.html
- PyTorch CUDA allocator and visualization:
  https://docs.pytorch.org/docs/stable/torch_cuda_memory.html
