# Memory Barrier Strategy

This document records the current strategy before implementing destructive
memory-management code.

## Principle

WorkflowDirector must first learn what the **current stable ComfyUI** does
naturally at a true top-level job boundary.

The original failure happened in an older environment while trying to
unload/switch a large GGUF model inside one prompt. That history motivates the
project but must not dictate the current implementation.

Current audited release: ComfyUI v0.39.0 on 2026-10-07.

## Boundary definition

A Workflow reaches the boundary only when its native ComfyUI job state is
terminal.

For normal forward execution, WorkflowDirector advances only from:

    status = completed

Live execution_success events are not sufficient because current ComfyUI emits
them before the PromptExecutor finalizer finishes.

## Barrier 0 — Current defaults, observe only

Run current stable ComfyUI with its normal memory behaviour.

After Workflow 1 reaches completed:

1. do not unload anything;
2. measure process RSS;
3. measure cgroup-aware runtime RAM headroom;
4. measure PyTorch allocated/reserved VRAM;
5. measure device-global CUDA used/free VRAM;
6. then submit Workflow 2.

Question:

> Does a real top-level job boundary already provide enough reusable/free memory
> for Workflow 2 to complete?

If yes, do not add custom cleanup merely to make a metric look lower.

## Barrier 1 — Controlled cache experiment

If memory retention prevents Workflow 2 from running, repeat the same experiment
with one controlled change at a time.

The first useful diagnostic may be:

    --cache-none

This tests whether executor caching is retaining objects across jobs.

It is a diagnostic setting, not an initial product requirement.

## Barrier 2 — Safe post-job cleanup experiment

If the failure persists, test a dedicated post-job cleanup step only after
Workflow 1 is terminal.

Candidate operations are limited initially to:

- Python garbage collection;
- Comfy dead-model cleanup;
- soft CUDA/PyTorch cache cleanup and synchronization.

Do not start by calling model_unload(), unload_all_models(), detach(), custom
HardDelete logic or forced CPU offload.

## Barrier 3 — Diagnose remaining references

If memory is still retained, inspect what remains alive before deleting
anything.

Questions:

- Is a ModelPatcher still referenced?
- Is a real model still alive?
- Is a current Comfy cache intentionally retaining it?
- Is the retained amount merely PyTorch reserved memory?
- Is device-global usage actually high?
- Is host RAM pressure coming from offload/pinning behaviour?
- Is a GGUF/custom-node object retaining mappings or tensors?

Current Comfy internals such as LoadedModel and current_loaded_models may be used
for diagnostics, but they are not part of WorkflowDirector's architectural
contract.

## Barrier 4 — Experimental targeted release

Only if diagnostics identify a specific stale reference should an explicit
release experiment be designed.

Any such mechanism must:

- run after the source Workflow is terminal;
- avoid overlapping the next Workflow;
- measure before/after;
- fail closed rather than continuing with uncertain memory state;
- remain isolated from Master/Context logic.

## Queue rule

The Master submits one top-level Workflow at a time:

    Workflow 1
       |
    native job = completed
       |
    observe / optional barrier
       |
    Workflow 2

The successor is not pre-queued while the barrier is being evaluated.

## Startup flags

Do not inherit the old notebook's memory flags into the new baseline.

Current Comfy defaults are the first test. Any switch such as cache-none,
disable-dynamic-vram, disable-async-offload or disable-pinned-memory is a
separate experiment whose effect is measured.

## Success criterion

The primary success criterion is not "all memory counters return to zero."

It is:

> Workflow 2 can load and complete reliably after Workflow 1, with measured RAM
> and VRAM staying inside safe limits and without restarting the Colab kernel.

Lower post-boundary memory is desirable, but functional safe reuse is the
product requirement.
