# Validation Plan

The implementation is validated in increasing levels of complexity.

## Release policy for every test

Use the **latest stable ComfyUI release tag** available when the test cycle
begins. Do not develop against the moving master branch.

Record the exact tag in the test log.

Current audited target on 2026-10-07:

    ComfyUI v0.39.0

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

## Phase 2 — Memory boundary

Goal: determine what current ComfyUI already releases naturally between two
independent top-level jobs.

Measure:

- process RSS;
- cgroup-aware runtime RAM available/total;
- PyTorch allocated/reserved VRAM;
- device-global CUDA used/free VRAM;
- values after Workflow 1 reaches terminal state;
- values immediately before Workflow 2;
- values during/after Workflow 2.

First test current defaults with **no custom cleanup**.

If memory remains a problem, vary one thing at a time. A useful first diagnostic
is `--cache-none`. DynamicVRAM, async offload and pinned-memory behaviour should
only be disabled in separate controlled experiments.

Success is functional: enough real RAM/VRAM is available for the next workflow
to load and complete without restarting the notebook/kernel. Near-baseline
memory is desirable but not required if retained memory is safely reusable.

## Phase 3 — Real heavy-model case

Only after Phase 2 succeeds, add the minimum current dependencies required for
the real model case, including a ComfyUI-GGUF version compatible with the current
stable ComfyUI.

Test conceptually:

    Workflow 1
      Qwen + Klein Q6 + prompt/LoRA stack A
           |
    real job boundary
           |
    Workflow 2
      Qwen + Klein Q6 + prompt/LoRA stack B

Do not assume the failure mechanism is identical to the old v0.37 environment.

Target:

- at least three consecutive W1 -> boundary -> W2 cycles;
- no whole notebook/kernel restart;
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
