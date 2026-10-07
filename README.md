# ComfyUI-WorkflowDirector

A visual workflow-level director for ComfyUI.

WorkflowDirector coordinates multiple independent ComfyUI workflows while
preserving shared Context between them and creating a real execution/memory
boundary between workflows.

## Compatibility policy

During the proof-of-concept phase, WorkflowDirector targets the **current stable
ComfyUI release**, not an old compatibility baseline and not the moving
`master` branch.

Current audited stable release on 2026-10-07: **ComfyUI v0.39.0**.

When ComfyUI publishes a new stable release, WorkflowDirector should move to it
after the compatibility review and laboratory tests pass. The exact ComfyUI tag
used by each test run must be recorded for reproducibility.

Older ComfyUI releases, including v0.37.0 where the original memory failure was
observed, are not support targets during this early phase.

## Why this exists

The original problem is practical: a large ComfyUI workflow can finish one
generation pass successfully but fail while unloading or switching large models
inside the same prompt. WorkflowDirector explores a different architecture:
let one workflow finish completely, observe/recover memory at a true workflow
boundary, then start the next workflow as a separate execution.

The goal is not to replace ComfyUI's visual workflow editor. Individual
workflows remain normal, editable and independently runnable ComfyUI workflows.

## Core concepts

- **Master** — the visual high-level process that determines workflow execution order.
- **Workflow** — a normal ComfyUI workflow that can also run independently.
- **Context** — arbitrary typed shared state that workflows may read, create, or replace.
- **Checkpoint** — an explicit saved snapshot of Context that can later be restored.
- **Memory Barrier** — the controlled boundary after one workflow has fully completed and before the next begins.

## First milestone

Before building the full UI, Context persistence, or checkpoint system, the
project must prove the reason it exists:

1. Run Workflow 1 as its own ComfyUI job.
2. Wait until the job reaches a terminal successful state.
3. Measure real process RAM, runtime RAM headroom and GPU memory.
4. Apply no cleanup unless measurements show it is needed.
5. Run Workflow 2 as a new ComfyUI job.
6. Repeat reliably without restarting the notebook/kernel.

Testing starts with a clean installation of the current stable ComfyUI release
and trivial workflows. Only after the boundary is proven do we add the minimum
dependencies needed for the real heavy-model case.

See:
- [Architecture](docs/ARCHITECTURE.md)
- [Compatibility policy](docs/COMPATIBILITY.md)
- [Validation plan](docs/VALIDATION_PLAN.md)
- [Phase 0 lab](docs/PHASE0_LAB.md)
- [Code review protocol](docs/CODE_REVIEW_PROTOCOL.md)
- [Memory barrier strategy](docs/MEMORY_BARRIER_STRATEGY.md)

## Status

Early design / proof-of-concept phase.
