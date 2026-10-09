# Glibc allocator census: design before changing the live ComfyUI process

**Context:** M-001 through M-003 (3 A→B cycles) identified PSS_Anon residual ~2.415 GiB vs baseline ~0.719 GiB. M-004 through M-006 identified 540 anonymous mapping regions totaling 2.087 GiB and, within them, 13 high-confidence glibc secondary-heap-shaped mappings of ~63MiB RW +1MiB PROT_NONE, exactly aligned 64MiB (818 MiB resident). See [MEMORY_EXPERIMENT_LOG.md](MEMORY_EXPERIMENT_LOG.md).

## What is proven and what is not

- The **geometry** of these 13 regions is an unusually strong fingerprint of glibc ptmalloc secondary heaps (`HEAP_MAX_SIZE`-aligned `mmap` followed by selective `mprotect`). Source: https://codebrowser.dev/glibc/glibc/malloc/arena.c.html. Exact glibc version and number of distinct arenas are **not** yet established.
- **818 MiB resident is not 818 MiB freed/unused.** A single arena can own multiple secondary heaps. The 13 regions are heaps/mappings rather than confirmed count of arenas.
- Neither `/proc/PID/smaps` nor ProfilerX can count free glibc chunks. They can show mapped pages/changes or per-node deltas but not the allocator's internal freelists. `MemAvailable` returned to 8.663GiB after third cycle; no justification for aggressive cleanup.
- The anónymous PSS net increase (~1.696 GiB) must not be attributed exclusively to the 818 MiB mappings since there is no pre-M-001 VMA-level baseline.

## Proposed follow-on controlled measurement (not implemented, NOT active)

**Question:** How much memory is in-use vs held on glibc allocator freelists across *all* ptmalloc arenas after a real A→B cycle?

- Glibc exports `malloc_info(0, FILE*)` as per https://man7.org/linux/man-pages/man3/malloc_info.3.html. Returns XML with arena entries, totals, system space and free chunks. It must execute **inside the exact ComfyUI PID**. A Colab notebook cell executing `malloc_info` will measure the notebook's process, not Comfy's.
- An optional **diagnostic-only** route/function could be added to `feature/memory-diagnostics`, guarded by a dedicated opt-in environment variable, with bounded output and read-only behavior. Implement/test it **outside live Comfy first**; enabled only in a fresh experimental Comfy process launched using original flags. No attaching debugger, ptrace, arbitrary memory reads, unloading or raw pointer dumps.
- Guard for real Comfy prompt_queue busy state as well as WorkflowDirector active_run_id. `active_run_id=None` alone does not exclude a direct UI job.
- Snapshot idle before A, directly after A→B, then settled; obtain both `malloc_info` summary and `smaps_rollup` from the same PID; compare RSS/PSS and glibc `system.current`, `fast`, `rest`, and `mmap` totals with clear semantics. Validate how much is reusable vs **releasable to OS**: those are not synonyms. XML aggregation must not double-count per-heap and global totals. Thread-local tcache may be counted differently from central free lists; `malloc_info` does **not** classify all torch-native or extension allocations.
- Native `malloc_info` is a glibc diagnostic call and is documented as MT-Safe but not mathematically zero-risk; it may acquire allocator locks, allocate a small amount to serialize, and perturb measurements. It must never run during model execution in acceptance tests. No live process injection, no `malloc_trim()` or tunable changes before a proper isolated baseline.
- Prepare rollback: disable opt-in route, restart **only the Comfy server process** with identical flags, confirm health, avoid reinstalling Torch/CUDA. This necessarily resets the process baseline; results must be treated as a new experiment, not a continuation of original PID 16744.
- Keep ProfilerX as a **separate subsequent experiment** to avoid confusing effects. If allocator census shows high free-space backlog, test potential mitigations only in a disposable isolated process with before/after and regression A→B.
- **Do not implement/enable without explicit go-ahead and independent unit/Colab acceptance.** Context PR #6 remains paused.

## Immediate next action

No further alignment-probing is needed. First review this design for safe measurement and compatibility, then decide whether to implement an opt-in diagnostic in the memory branch. Do not ask the user to run another A/B loop to guess at heap ownership.
