# Phase 2 — Non-destructive memory observation

Current development runtime mode:

    observe-phase2-nondestructive

This phase measures memory around true top-level Workflow boundaries. It does
not unload models, reset executor caches, call /free, or invoke
unload_all_models().

## Run-level baseline

Before Workflow A is submitted:

1. verify that Comfy has no pending/in-progress jobs;
2. perform one discarded memory-snapshot warm-up;
3. verify the queue again;
4. capture BASELINE;
5. verify the queue again.

The discarded warm-up prevents first-use CUDA/device initialization from being
misread as baseline consumption.

## Per-Workflow boundary

After the native Jobs API reports the Workflow terminal:

1. verify that no unrelated job is active;
2. capture POST_IMMEDIATE;
3. verify the queue again;
4. observe an idle window;
5. poll for foreign active jobs throughout that window;
6. capture POST_WINDOW_END between queue checks;
7. only then allow the next Workflow preflight.

The default observation window is 1.0 second and can be changed before ComfyUI
starts with:

    WORKFLOWDIRECTOR_OBSERVATION_SECONDS=<seconds>

This window is diagnostic only. It is **not** a garbage-collection trigger and
does not imply that memory is settled.

## Measurements

memory_snapshot currently records:

- process RSS;
- cgroup-aware system RAM total/available/unavailable;
- Comfy's selected device;
- PyTorch CUDA allocated/reserved memory;
- PyTorch peak counters since their last reset;
- device-global CUDA used/free/total memory;
- a diagnostic count of entries in Comfy's current_loaded_models registry.

The model-registry metric reads only the list length. It deliberately avoids
creating a temporary list of strong model references while a boundary is being
measured.

Peak counters are not yet reset per Workflow and therefore are not used for
per-Workflow pass/fail conclusions.

## Important v0.39.0 findings

### Idle time is not proof of worker GC

The prompt worker has a nominal 10-second GC interval, but its current_time value
is updated after executing a queue item. When an idle q.get(timeout=...) returns
None, current_time is not advanced in that path. Therefore simply sleeping for
more than 10 seconds cannot be treated as proof that normal worker
GC/soft_empty_cache ran.

### PromptModelTracker.end() is not an unload

PromptModelTracker.end() marks tracked dynamic model patchers as no longer in
use by the current prompt and clears the tracker's own mapping. It does not
empty Comfy's current_loaded_models registry.

### /free is not a safe cache-only barrier

In v0.39.0, free_memory=true falls back to model unloading in the worker and can
reach unload_all_models(). WorkflowDirector excludes that endpoint from the
initial safe path.

## Queue integrity

The current build:

- allows only one WorkflowDirector Master run at a time;
- checks native pending/in-progress jobs before baseline and before each submit;
- brackets baseline and boundary snapshots with queue checks;
- polls for foreign jobs during the observation window.

This reduces accidental contamination but is not yet a hard queue lease. A very
short unrelated job could theoretically enter and finish between polls.

For the Colab validation, Auto Queue must be disabled and no unrelated workflow
should be queued while a Director run is active.

## Next experiment

Run the same real Workflow A in two controlled configurations:

1. current Comfy defaults;
2. identical environment plus --cache-none.

Compare BASELINE, POST_IMMEDIATE and POST_WINDOW_END.

Only after those measurements exist should WorkflowDirector decide whether a
separate GC/allocator-only experiment is necessary.
