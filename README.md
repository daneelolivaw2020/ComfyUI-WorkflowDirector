# ComfyUI-WorkflowDirector

A visual workflow-level director for ComfyUI.

The project is intended to coordinate multiple independent ComfyUI workflows while preserving a shared Context between them and, critically, creating a real execution/memory boundary between workflows.

## Why this exists

The original problem is practical: a large ComfyUI workflow can finish one generation pass successfully but fail when unloading or switching large models inside the same prompt. WorkflowDirector explores a different architecture: let one workflow finish completely, verify/recover memory, then start the next workflow as a separate execution.

The goal is not to replace ComfyUI's visual workflow editor. Individual workflows should remain normal, editable and independently runnable ComfyUI workflows.

## Core concepts

- **Master** — the visual high-level process that determines workflow execution order.
- **Workflow** — a normal ComfyUI workflow that can also run independently.
- **Context** — arbitrary typed shared state that workflows may read, create, or replace.
- **Checkpoint** — an explicit saved snapshot of Context that can later be restored.
- **Memory Barrier** — the boundary after one workflow has fully completed and before the next begins.

## First milestone

Before building the full UI, Context persistence, or checkpoint system, the project must prove the reason it exists:

1. Run Workflow 1.
2. Wait for true prompt completion.
3. Recover GPU/system memory outside the running prompt.
4. Verify memory returned close to baseline.
5. Run Workflow 2.
6. Repeat reliably without restarting the notebook/kernel.

Testing starts with a minimal ComfyUI installation and very small workflows. Only after the mechanism works do we reproduce the original heavy-model case.

See:
- [Architecture](docs/ARCHITECTURE.md)
- [Validation plan](docs/VALIDATION_PLAN.md)
- [Phase 0 lab](docs/PHASE0_LAB.md)

## Status

Early design / proof-of-concept phase.
