# Code Review Protocol

WorkflowDirector is being built around a memory-lifecycle problem, so every
non-trivial code change should pass two distinct reviews before it is considered
ready for a Colab test.

## Review A — Compatibility and correctness

Check the code against the pinned ComfyUI version used by the laboratory.

Questions include:

- Does the ComfyUI API actually exist in the pinned version?
- Is the custom-node loading mechanism valid?
- Are execution/cache semantics being interpreted correctly?
- Are metrics labelled according to what they really measure?
- Can unchanged nodes be cached when the test requires re-execution?
- Are imports/dependencies already supplied by the pinned ComfyUI build?

## Review B — Adversarial lifecycle and failure review

Assume the happy path is misleading.

Questions include:

- Could ComfyUI still hold references after the event we call "finished"?
- Could a measurement itself change CUDA state?
- Are we confusing PyTorch allocator memory with total device usage?
- Could a partial failure mutate persistent state?
- Could cleanup run concurrently with an active prompt?
- Could an identical prompt be served from cache and invalidate the experiment?
- Is the worker idle while another prompt is already pending?
- What happens if ComfyUI, the backend process, or the Colab kernel dies?

## Phase 0 review findings

### Finding 1 — Test Marker could be cached

**Status: fixed.**

The original marker had no IS_CHANGED implementation. Repeated identical queues
could therefore reuse cached output instead of executing the marker and taking
a fresh measurement.

The node now returns NaN from IS_CHANGED, forcing execution on every run.

### Finding 2 — Process RSS alone is insufficient

**Status: fixed.**

The original instrumentation measured process RSS but not the cgroup-aware
system RAM headroom that matters on Colab. It now uses ComfyUI's
comfy.system_memory.virtual_memory_total() and virtual_memory_available(), plus
process RSS.

CUDA metrics explicitly distinguish PyTorch allocated/reserved memory from
device-global used/free memory.

### Finding 3 — execution_success is too early for the Memory Barrier

**Status: architecture corrected; implementation intentionally deferred.**

In ComfyUI v0.37.0, execution_success is emitted inside
PromptExecutor.execute_async(). Its finally block runs afterwards and calls
prompt_model_tracker.end(). Only after that does PromptExecutor.execute() return
to the queue worker, which commits history and removes the prompt from the
running set.

Therefore WorkflowDirector must not begin memory cleanup merely because it saw
execution_success. The first Memory Barrier prototype must verify that the
prompt is no longer running.

### Finding 4 — "No running prompt" is not the same as "queue empty"

**Status: fixed in diagnostics.**

The diagnostic status route now reports worker_idle and queue_empty separately.
The future Memory Barrier should require that its target prompt is no longer
running and, in the one-at-a-time Master design, that no successor prompt has
already been queued.

### Finding 5 — the first CUDA measurement can perturb the baseline

**Status: accounted for in the lab procedure.**

The lab now performs one warm-up memory query before recording the baseline.
This prevents CUDA-context initialization from being mistaken for model memory.

### Compatibility checks passed

For ComfyUI v0.37.0:

- legacy NODE_CLASS_MAPPINGS custom-node registration is still supported;
- PromptServer.instance.routes is a supported custom-route pattern;
- PromptQueue.get_current_queue_volatile() exists;
- prompt queue items store prompt_id at index 1 in the /prompt path;
- psutil is present in ComfyUI's pinned requirements.
