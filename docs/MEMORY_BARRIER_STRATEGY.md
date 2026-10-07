# Memory Barrier Strategy

This document records the current strategy before implementing destructive
memory-management code.

## Why the order matters

The original failure happened while trying to unload/switch a large GGUF model
inside the same prompt.

ComfyUI v0.37.0 changes the situation after a real prompt boundary:

- PromptModelTracker.end() runs in the PromptExecutor finalizer.
- LoadedModel stores its ModelPatcher through a weak reference.
- With --cache-none, ComfyUI uses NullCache for both output and object caches.

Those facts make natural post-prompt release plausible and worth testing before
adding custom deletion logic.

They do **not** prove that GGUF will release correctly. That remains an empirical
question.

## Barrier experiments must be incremental

### Barrier 0 — Observe only

After Workflow 1 has completely left the running queue:

1. do not unload anything;
2. measure process RSS, system RAM headroom, PyTorch allocated/reserved VRAM and
   device-global used/free VRAM;
3. allow a short synchronization/observation point if needed;
4. measure again.

Question:

> Does true prompt completion plus --cache-none already release enough memory?

If yes, custom destructive cleanup is unnecessary.

### Barrier 1 — GC/cache cleanup only

If Barrier 0 leaves stale memory, run a **separate tiny top-level prompt** after
Workflow 1. It executes on ComfyUI's normal prompt worker, but is not part of
Workflow 1.

The first cleanup experiment should be limited to operations such as:

- Python garbage collection;
- ComfyUI dead-model cleanup;
- CUDA/PyTorch soft cache emptying and synchronization.

It must not call model_unload(), unload_all_models(), detach(), unpatch_model(),
or move a model to CPU.

Why a separate barrier prompt is attractive:

- Workflow 1's PromptExecutor finalizer has already run;
- prompt-tracked models are no longer marked as in use;
- the barrier runs on ComfyUI's normal worker thread rather than an HTTP thread;
- its execution and console output remain observable like any other prompt.

### Barrier 2 — Diagnose remaining references

If memory is still retained, inspect model registry state and reference
liveness. Do not immediately escalate to unloading.

Questions:

- Is the ModelPatcher still alive?
- Is a real model still alive?
- Is a cache or custom node retaining it?
- Is the memory PyTorch-reserved memory only, or real device usage?
- Is RAM pressure caused by an attempted offload?

### Barrier 3 — Experimental registry release

Only if the previous steps prove that a stale registry/reference is the reason
memory remains should WorkflowDirector test explicit registry removal.

Any such experiment must happen in a separate barrier prompt, never inside the
workflow whose model is being released.

This phase is intentionally undefined until Barrier 0/1 diagnostics show what
is actually retained.

## Queue rule

The Master should queue one top-level job at a time:

    Workflow 1
       |
    wait until not running
       |
    Barrier
       |
    wait until not running
       |
    Workflow 2

The successor Workflow must not already be pending when the barrier starts.

## Initial runtime requirement

For the first proof of concept, run ComfyUI with --cache-none.

The final project may later support other cache modes, but persistent executor
caches can legitimately keep workflow outputs alive across prompts and would
confound the memory-isolation experiment.

## Explicitly excluded from the first tests

Do not use:

- ComfyUI /free with unload_models;
- unload_all_models();
- ordinary unload custom nodes;
- HardDelete inside Workflow 1;
- CPU offload as a substitute for releasing the model.

The purpose of the experiment is to determine whether a true workflow boundary
can avoid the RAM spike that caused the original kernel restart.
