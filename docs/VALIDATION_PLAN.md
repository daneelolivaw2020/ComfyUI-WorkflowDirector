# Validation Plan

The implementation must be validated in increasing levels of complexity.

## Phase 0 — Minimal environment

Install only what is required for the current test.

Start with:

- ComfyUI v0.37.0;
- ComfyUI-WorkflowDirector.

Add other custom nodes only when a test specifically requires them.

The test notebook should be separate from the existing large production notebook.

## Phase 1 — Independent workflow execution

Goal: prove that WorkflowDirector can execute two separate ComfyUI workflows in sequence.

Use deliberately trivial workflows.

Success criteria:

- Workflow 1 runs normally.
- Workflow 1 reaches true completion.
- Workflow 1 is no longer present in ComfyUI's running queue.
- Workflow 2 starts only after that condition is true.
- execution events/errors remain observable.

Do not use execution_success by itself as the definition of prompt completion:
in ComfyUI 0.37 it is emitted before the PromptExecutor finalizer calls
prompt_model_tracker.end().

No heavy models are needed yet.

## Phase 2 — Memory Barrier

Goal: prove that memory can be recovered between independent top-level workflow executions.

Measure at least:

- process RSS;
- cgroup-aware system RAM available/total;
- baseline PyTorch allocated/reserved VRAM;
- device-global CUDA used/free VRAM;
- peak VRAM during Workflow 1;
- memory immediately after the prompt has left the running queue;
- memory after the Memory Barrier.

Success should be defined by enough real RAM/VRAM returning to safely load the
next model, not merely by PyTorch reserved memory decreasing.

The test must avoid ordinary in-workflow unload nodes.

## Phase 3 — Reproduce the original heavy-model problem

Only after Phase 2 succeeds, add the minimum dependencies necessary for the real target case.

Test:

    Workflow 1
      Klein Q6 + prompt/LoRA stack A
           |
    Memory Barrier
           |
    Workflow 2
      Klein Q6 + prompt/LoRA stack B

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
