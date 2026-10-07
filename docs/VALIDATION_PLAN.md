# Validation Plan

## Non-negotiable acceptance environment

Every phase that touches execution or memory must ultimately pass on:

    Google Colab Free Tier
    NVIDIA T4
    standard-memory runtime

Larger GPUs may be useful for diagnosis, but they cannot be used to declare a
phase successful. Do not compensate for a memory failure by moving the target to
A100/L4/High-RAM.

The lab must also assume /content is ephemeral and that runtime loss is possible.

The implementation is validated in increasing levels of complexity.

## Release policy for every test

Use the **latest stable ComfyUI release tag** available when the test cycle
begins. Do not develop against the moving master branch.

Record the exact tag in the test log.

See COMPATIBILITY.md for the currently audited stable release.

## Phase 0 — Clean current environment

Install only:

- current stable ComfyUI;
- ComfyUI-WorkflowDirector.

Start with ComfyUI's current default memory behaviour. Do not copy the old
notebook's diagnostic memory flags into the new laboratory.

In particular, do not initially force:

- --cache-none;
- --disable-dynamic-vram;
- --disable-async-offload;
- --disable-pinned-memory.

Those become controlled diagnostic variables only if a later test needs them.

The lab notebook must be separate from the production notebook.

## Phase 1 — Independent workflow execution

Goal: prove that WorkflowDirector can execute two separate ComfyUI jobs in
sequence.

Use deliberately trivial workflows.

Success criteria:

- Workflow 1 runs normally;
- its WebSocket events remain observable;
- the native Jobs API eventually reports `completed`;
- Workflow 2 is submitted only after that terminal state;
- Workflow 2 also reaches `completed`;
- errors stop the sequence instead of advancing it.

No heavy models are needed yet.

## Phase 2 — Real model use and memory behaviour

Phase 2 answers several distinct questions. They must not be collapsed into one
"did memory unload?" result.

### 2A — Prove the models were really used

Loader nodes alone are not sufficient because model movement/loading may be
deferred until use.

Workflow A must produce a real image and genuinely exercise:

- GGUF diffusion-model loader;
- GGUF text-encoder loader;
- text encoding;
- VAE loader;
- sampler;
- VAE decode;
- image preview/save.

For the target case, use Klein Q6, the intended Qwen text encoder, and the same
known-working VAE/model-specific sampling path as the production workflow.

Workflow A contains **no unload node**.

### 2B — Execution boundary vs memory boundary

The native Jobs API reporting `completed` proves the Workflow execution has
ended. It does **not** by itself prove that all model memory has been released.

Current ComfyUI may still:

- retain node outputs in its executor cache;
- retain reusable model state by design;
- run worker housekeeping/GC after the job has already entered history.

Therefore use this sequence:

    CUDA warm-up
        |
    BASELINE
        |
    Workflow A: real image
        |
    Jobs API = completed
        |
    POST_A_IMMEDIATE
        |
    remain idle; do not queue B
        |
    POST_A_SETTLED
        |
    only then continue

POST_A_IMMEDIATE records the state as soon as the job is terminal.
POST_A_SETTLED records the state after the worker has had time to perform its
normal post-job housekeeping. Because current ComfyUI's worker GC interval is
10 seconds, the laboratory should include an idle observation after that
interval rather than drawing conclusions from one immediate snapshot.

### 2C — Current-default cache observation

Current ComfyUI's default RAM-pressure cache can intentionally retain outputs
from previous jobs, including ModelPatcher-producing loader nodes, until memory
pressure causes eviction.

Therefore the default-cache run answers:

> Can current ComfyUI transition safely to the next Workflow under its normal
> caching/memory policy?

It does **not** by itself answer:

> Was the first model fully released?

Retained memory under the default cache is not automatically a WorkflowDirector
bug.

### 2D — Isolation/release experiment

If we specifically want to test whether a true workflow boundary can release
model references, repeat the same A-only experiment with one controlled change:

    --cache-none

Then compare BASELINE, POST_A_IMMEDIATE and POST_A_SETTLED.

This removes the normal executor output cache as a confounder. It still does not
guarantee that GGUF/model-management references disappear; that is what the
experiment measures.

Do not add unload nodes or explicit destructive cleanup at this stage.

### 2E — Practical A -> B transition proof

After the A-only observations are recorded, run Workflow B as a new top-level
job.

For the first practical Klein test, B may use the same Klein Q6/Qwen/VAE path
with a different prompt. This proves sequencing/reuse safety, **not unload**.

Then repeat with:

- LoRA stack A in Workflow A;
- LoRA stack B in Workflow B.

This is the real target scenario.

A stronger future generalization test may use a genuinely different heavy model
in B. That is useful for proving model-switching capability but is not required
before the original Klein use case works.

### Metrics

Record:

- process RSS;
- cgroup-aware runtime RAM available/total;
- PyTorch allocated/reserved VRAM;
- device-global CUDA used/free VRAM.

Do not use the current `peak_*_since_reset` fields for per-Workflow conclusions
until WorkflowDirector implements an explicit peak-reset protocol.

Reserved VRAM alone is not proof that a model remains live.

### Phase 2 success

There are two different success statements:

**Release observation:** memory after A is understood and measured without
confounding it with W1-internal unload logic.

**Functional transition:** Workflow B can execute safely after A on Colab Free
T4 without host-RAM spike, OOM, or kernel restart.

## Phase 3 — Real heavy-model regression

Only after Phase 2 succeeds, add the minimum current dependencies required for
the real model case, including a ComfyUI-GGUF version compatible with the current
stable ComfyUI.

Test:

    Workflow 1
      Qwen + Klein Q6 + prompt/LoRA stack A
           |
    execution boundary
           |
    memory observation / barrier
           |
    Workflow 2
      Qwen + Klein Q6 + prompt/LoRA stack B

Target on the mandatory Colab Free T4 environment:

- at least three consecutive W1 -> boundary -> W2 cycles;
- no whole notebook/kernel restart;
- no paid/High-RAM runtime requirement;
- memory measurements recorded at every boundary.

## Phase 4 — Minimal Context

After the execution/memory architecture is proven, add shared Context.

First supported types:

- STRING
- IMAGE
- LATENT

Prove that Workflow 1 can publish values and Workflow 2 can consume them without
forcing the workflows into one giant ComfyUI prompt.

Context keys must be arbitrary.

## Phase 5 — Persistence and Checkpoints

Only after local Context works:

- persist Context metadata/assets;
- use fast local scratch storage during execution;
- commit durable state to Google Drive only after successful workflow completion;
- add explicit Checkpoints;
- support resume from a Checkpoint.

## Phase 6 — Visual integration

Then build the full ComfyUI-facing experience:

- Master canvas;
- Workflow nodes;
- Checkpoint nodes;
- workflow tabs/opening;
- follow-execution mode;
- Context panel;
- live console panel;
- retry/resume controls.

## Guiding rule

Each phase answers one technical question. If a lower phase fails, fix it before
building higher-level UI or persistence.
