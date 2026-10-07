# Memory Barrier Strategy

This document records the current strategy before implementing destructive
memory-management code.

## Principle

WorkflowDirector must first learn what the **current stable ComfyUI** does
naturally at a true top-level job boundary.

See COMPATIBILITY.md for the currently audited stable release.

## Two different boundaries

WorkflowDirector must not confuse execution completion with memory quiescence.

### Execution boundary

Reached when the native Jobs API reports:

    status = completed

At this point the Workflow has finished and transactional Context may eventually
be committed.

### Memory boundary

Reached only after WorkflowDirector has evaluated the post-job memory state and,
if required, completed its memory-barrier policy.

The execution boundary is necessary but not sufficient to claim that model
memory has been released.

## Why current defaults can retain models

Current ComfyUI uses RAM-pressure caching by default.

Its executor cache persists across jobs and may retain outputs from loader nodes.
The current RAMPressureCache specifically gives old ModelPatcher outputs high
eviction priority under RAM pressure, which means such objects can remain cached
when pressure is low.

Therefore:

- default-cache retention may be intentional;
- `job = completed` does not imply loader outputs disappeared;
- using the same model in Workflow B can prove reuse/transition but cannot prove
  Workflow A unloaded it.

## Post-job housekeeping timing

Current ComfyUI's prompt worker marks a job done before the later section that
may call Python GC and soft_empty_cache().

However, source review of v0.39.0 shows that merely waiting past the nominal
10-second GC interval is not a reliable trigger. The worker updates its
current_time after executing a queue item; when q.get(timeout=...) returns None
while idle, that variable is not advanced in that path. Therefore an idle timer
alone cannot be used as proof that housekeeping ran.

The laboratory still records:

    POST_A_IMMEDIATE
    POST_A_WINDOW_END

but POST_A_WINDOW_END means only "end of the configured observation window".
It is useful for observing natural memory drift and validating that no foreign
job entered the boundary. It does not assert GC or memory stability.

Workflow B is not queued during this observation window.

## Barrier 0 — Current defaults, observe only

Run current stable ComfyUI with normal memory behaviour.

After Workflow A reaches completed:

1. do not unload anything;
2. take POST_A_IMMEDIATE;
3. remain idle;
4. take POST_A_WINDOW_END;
5. interpret cache retention separately from actual memory pressure;
6. only then decide whether to submit B.

Question:

> Can current ComfyUI transition safely to the next Workflow under its normal
> memory/cache policy?

This is a compatibility observation, not a strict unload test.

## Barrier 1 — Cache-isolation experiment

Repeat the same Workflow A with:

    --cache-none

This removes executor output caching as a confounding source of strong
references.

Question:

> Once the normal executor cache is removed from the experiment, what model/RAM/
> VRAM state remains after a true job boundary and normal worker housekeeping?

Do not add unload nodes.

## Native /free is not the safe cache-only primitive

In ComfyUI v0.39.0, /free with free_memory=true ultimately reaches
unload_all_models() through the prompt worker's fallback:

    flags.get("unload_models", free_memory)

The HTTP route only records true flags, so supplying unload_models=false does
not create an independent cache-only mode.

WorkflowDirector therefore excludes /free from the initial safe barrier.

## Barrier 2 — Safe post-job cleanup experiment

Only if the cache-isolation experiment still leaves problematic memory, design a
dedicated post-job cleanup step that does **not** route through /free or
unload_all_models().

Candidate operations may include, after source review and isolated testing:

- Python garbage collection;
- cleanup of references already proven dead;
- soft CUDA/PyTorch allocator cleanup and synchronization.

Do not start by calling model_unload(), unload_all_models(), detach(), custom
HardDelete logic or forced CPU offload.

## Barrier 3 — Diagnose remaining references

If memory is still retained, inspect what remains alive before deleting
anything.

Questions:

- Is a ModelPatcher still strongly referenced?
- Is a real model still alive?
- Is model-management intentionally retaining reusable state?
- Is retained memory merely PyTorch reserved memory?
- Is device-global usage actually high?
- Is host RAM pressure coming from offload/pinning behaviour?
- Is a GGUF/custom-node object retaining mappings or tensors?

Comfy internals may be used for laboratory diagnostics, but they are not part of
WorkflowDirector's architectural contract.

## Barrier 4 — Experimental targeted release

Only if diagnostics identify a specific stale reference should an explicit
release mechanism be designed.

Any such mechanism must:

- run after the source Workflow is terminal;
- avoid overlapping the next Workflow;
- measure before/after;
- fail closed rather than continuing with uncertain memory state;
- remain isolated from Master/Context logic.

## Queue rule

The Master submits one top-level Workflow at a time:

    Workflow A
       |
    native job = completed
       |
    post-job observation / barrier
       |
    Workflow B

The successor is not pre-queued while the memory boundary is being evaluated.

## Success criterion

The product requirement is not that every memory counter returns to zero.

The requirements are:

1. WorkflowDirector understands whether memory is cached, live or safely
   reusable at the boundary.
2. The next intended Workflow can load and complete on Colab Free T4 without
   unsafe host-RAM pressure, OOM or kernel restart.
3. If a Workflow genuinely requires release rather than reuse, the barrier can
   create enough headroom safely.
