# Validation Plan

The implementation must be validated in increasing levels of complexity.

## Phase 0 — Minimal environment

Install only what is required for the current test.

Start with:

- pinned ComfyUI version;
- ComfyUI-WorkflowDirector.

Add other custom nodes only when a test specifically requires them.

The test notebook should be separate from the existing large production notebook.

## Phase 1 — Independent workflow execution

Goal: prove that WorkflowDirector can execute two separate ComfyUI workflows in sequence.

Use deliberately trivial workflows.

Success criteria:

- Workflow 1 runs normally.
- Workflow 1 reaches true completion.
- Workflow 2 starts only after Workflow 1 has completed.
- execution events/errors remain observable.

No heavy models are needed yet.

## Phase 2 — Memory Barrier

Goal: prove that memory can be recovered between independent top-level workflow executions.

Measure at least:

- baseline VRAM;
- peak VRAM during Workflow 1;
- VRAM immediately after Workflow 1;
- VRAM after Memory Barrier;
- RAM before/after the barrier.

Success should be defined by memory returning close enough to baseline to safely load the next model, not merely by reserved CUDA memory decreasing.

The test must avoid ordinary in-workflow unload nodes.

## Phase 3 — Reproduce the original heavy-model problem

Only after Phase 2 succeeds, add the minimum dependencies necessary for the real target case.

Test:

```text
Workflow 1
  Klein Q6 + prompt/LoRA stack A
       |
Memory Barrier
       |
Workflow 2
  Klein Q6 + prompt/LoRA stack B
```

The important criterion is repeatability. A single successful run is not enough.

Target:

- at least three consecutive W1 -> barrier -> W2 cycles;
- no whole notebook/kernel restart;
- memory measurements recorded at every boundary.

## Phase 4 — Minimal Context

After the memory architecture is proven, add shared Context.

First supported types:

- STRING
- IMAGE
- LATENT

Prove that Workflow 1 can publish values and Workflow 2 can consume them without forcing the Workflows to become dependent on a single giant ComfyUI prompt.

Context keys must be arbitrary.

## Phase 5 — Persistence and Checkpoints

Only after local Context works:

- persist Context metadata/assets;
- use fast local scratch storage during execution;
- commit durable state to Google Drive after successful workflow completion;
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

Each phase must answer one technical question. If a lower phase fails, fix it before building higher-level UI or persistence.
