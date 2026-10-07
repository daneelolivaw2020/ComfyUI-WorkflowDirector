# Code Review Protocol

WorkflowDirector is built around execution and memory lifecycle, so every
non-trivial change passes two distinct reviews before it is considered ready for
a Colab test.

## Review A — Current compatibility and correctness

Review against the **current stable ComfyUI release tag**, never against an old
release merely because it was previously used.

Questions include:

- Is this the current official stable release?
- Does the ComfyUI API actually exist in that release?
- Are we using the current API instead of a supported-but-legacy path?
- Are execution/cache semantics being interpreted correctly?
- Are metrics labelled according to what they actually measure?
- Are dependencies already supplied by current ComfyUI?
- Can a public/native Comfy interface replace an internal implementation detail?

## Review B — Adversarial lifecycle and failure review

Assume the happy path is misleading.

Questions include:

- Could ComfyUI still hold references after the event we call "finished"?
- Are we confusing live WebSocket events with durable terminal job state?
- Could a measurement itself initialize or perturb CUDA state?
- Are we confusing PyTorch allocator memory with total device usage?
- Could a partial failure mutate persistent Context?
- Could cleanup overlap a running or queued successor workflow?
- Could caching invalidate the experiment?
- Are we carrying diagnostic flags from an obsolete environment?
- What happens if ComfyUI, the backend process or the Colab kernel dies?

## Current audit — ComfyUI v0.39.0

Audit date: 2026-10-07.

### Finding 1 — v0.38.0 was no longer latest

**Status: corrected.**

The project policy is latest stable. The official latest release on the audit
date is v0.39.0, so the current audit targets v0.39.0 rather than v0.38.0.

### Finding 2 — node registration used the legacy V1 API

**Status: fixed.**

V1 NODE_CLASS_MAPPINGS remains supported, but the current official example uses
the V3 ComfyExtension / io.ComfyNode API. The Phase 0 node and package entrypoint
now use V3.

### Finding 3 — custom queue-status route duplicated internal state

**Status: fixed.**

The earlier diagnostic route read PromptQueue internals directly. ComfyUI v0.39
has a native Jobs API with explicit pending, in_progress, completed, failed and
cancelled states. WorkflowDirector now intends to use that API for job lifecycle
and no longer exposes its own queue-status route.

### Finding 4 — execution_success is still too early

**Status: architecture corrected.**

In v0.39.0, execution_success is emitted before the PromptExecutor finalizer.
The finalizer then runs prompt_model_tracker.end() and lifecycle end handling.
Only after PromptExecutor returns does the worker call task_done(), placing the
job in history.

Therefore:

- WebSocket execution_success is useful live feedback;
- native Jobs API terminal state is the Master sequencing/commit signal.

### Finding 5 — old diagnostic memory flags would bias the new baseline

**Status: corrected in the validation plan.**

Current ComfyUI uses RAM-pressure caching by default and can enable DynamicVRAM
on supported NVIDIA systems. The clean lab now starts with current defaults.
Flags such as --cache-none or --disable-dynamic-vram are tested only as isolated
diagnostic variables if needed.

### Finding 6 — memory measurements needed to follow Comfy's selected device

**Status: fixed.**

The instrumentation now queries the device selected by ComfyUI rather than
assuming the process's current CUDA device is necessarily the target device.

### Finding 7 — first CUDA measurement can perturb the baseline

**Status: accounted for.**

Phase 0 performs one warm-up memory query and records the second reading as the
baseline.

### Current compatibility checks passed

Verified against the v0.39.0 source:

- V3 ComfyExtension / io.ComfyNode registration exists;
- output nodes with outputs=[] are supported;
- fingerprint_inputs can force re-execution;
- custom routes through PromptServer.instance.routes are supported;
- comfyui_version.__version__ is available;
- native /api/jobs/{job_id} support is present;
- cgroup-aware RAM helpers are present;
- psutil remains a ComfyUI dependency.


### Finding 8 — audited version was duplicated across documents

**Status: fixed.**

The exact audited ComfyUI version is now centralized in COMPATIBILITY.md.
Architecture and test documents refer to that source of truth instead of
copying a release number that can become stale at different times.

### Second-pass verification

The corrected code was checked again against the exact v0.39.0 tag.

Verified:

- the v0.39.0 V3 node API supports `outputs=[]` with `is_output_node=True`;
- v0.39.0 uses `fingerprint_inputs` for V3 cache invalidation and core code
  itself uses `float("NaN")` to force re-execution;
- v0.39.0 supports `io.NodeOutput(ui=...)`;
- the native single-job endpoint is exactly `/api/jobs/{job_id}`;
- a terminal Jobs API record comes from history after the prompt worker calls
  `PromptExecutor.execute()` and then `task_done()`;
- the code no longer needs a WorkflowDirector-specific queue-status endpoint.

## Review result

The current Phase 0 code is **statically ready for runtime validation** against
the audited stable release.

This does not claim that it has run successfully in Colab yet. Runtime loading,
CUDA measurements and the two-job lifecycle still require the laboratory test.


### Finding 9 — same-model A -> B does not prove unload

**Status: validation corrected.**

If Workflow B uses the same Klein model as A, B may succeed by reusing retained
state. That is valuable for the practical use case but does not prove model
memory was released.

The validation plan now separates A-only release observation from A -> B
transition/reuse testing.

### Finding 10 — current default cache can intentionally retain loader outputs

**Status: validation corrected.**

ComfyUI v0.39.0 uses RAM-pressure caching by default. The executor cache persists
across jobs, and RAMPressureCache can retain ModelPatcher-producing loader
outputs until pressure triggers eviction.

Therefore a default-cache run is not a strict unload test. `--cache-none` is
now the controlled cache-isolation experiment rather than merely a fallback
after a supposed unload failure.

### Finding 11 — terminal job state precedes optional worker GC

**Status: validation corrected.**

The prompt worker calls `task_done()` before its later housekeeping block.
Normal worker GC/soft cache cleanup uses a 10-second interval.

The test now distinguishes POST_A_IMMEDIATE from POST_A_SETTLED instead of
drawing conclusions from one snapshot immediately after `completed`.

### Finding 12 — peak CUDA metrics are not per-workflow yet

**Status: documented limitation.**

The current instrumentation exposes PyTorch peak values since the last reset,
but WorkflowDirector does not yet reset those counters per Workflow. They must
not be used for per-Workflow pass/fail decisions until a reset protocol is
implemented.

### Reasoning review result

The corrected first memory test now answers three separate questions:

1. Were MODEL/CLIP/VAE genuinely exercised?
2. What memory/cache state remains after A alone?
3. Can B run safely after the boundary?

Those questions are no longer conflated.
