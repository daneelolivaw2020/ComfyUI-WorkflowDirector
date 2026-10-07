# Architecture

## Design goal

WorkflowDirector should feel like a native visual layer on top of ComfyUI rather
than a separate script-driven system.

The intended user experience is eventually:

    [ MASTER ] [ Workflow 1 ] [ Workflow 2 ] [ Workflow 3 ]

Each individual Workflow remains a normal ComfyUI document. The Master
coordinates them at a higher level.

## Master

The Master defines high-level execution order.

    START
      |
    Workflow 1
      |
    Checkpoint (optional)
      |
    Workflow 2
      |
    ...
      |
    END

Master connections primarily represent execution dependency, not every piece of
data passed between workflows.

## Workflow

A Workflow:

- is a normal ComfyUI workflow;
- can be opened and tested independently;
- can read selected values from Context;
- can publish new or replacement values to Context;
- runs as its own top-level ComfyUI job.

## Context

Context is deliberately schema-light.

    KEY -> TYPE -> VALUE

Key names are arbitrary. WorkflowDirector must not hard-code names such as
current_image, current_prompt or current_latent.

Initial cross-workflow data types:

- STRING
- IMAGE
- LATENT

Other types can be added later without changing the core model.

## Checkpoint

A Checkpoint is an explicit saved snapshot of Context.

Checkpointing is intentionally simpler than full history/versioning. History,
provenance, branching and undo are outside the initial scope.

## Execution state

Use two different channels for two different purposes:

- **WebSocket execution events** provide live UI feedback: active node,
  progress, previews, errors and execution messages.
- **Native Jobs API** provides the authoritative job state used by the Master to
  decide whether it may commit Context or continue to the next Workflow.

A successful workflow boundary is reached only when the submitted job reports
the terminal state `completed`.

`execution_success` alone is not the boundary. In the currently audited stable release (see COMPATIBILITY.md) it is emitted
before the PromptExecutor finalizer runs.

## Memory Barrier

The Memory Barrier exists between two top-level ComfyUI jobs.

    Workflow N job
       |
    live WebSocket events
       |
    native job status = completed
       |
    measure RAM / VRAM
       |
    optional post-job cleanup only if required
       |
    measure again
       |
    submit Workflow N+1

The Master submits one Workflow at a time. The successor should not already be
queued while the barrier is being evaluated.

No unload node inside Workflow N is considered a valid memory boundary.

## Observability

The final UI should preserve normal ComfyUI feedback:

- active workflow visible;
- active node highlighting;
- sampler progress;
- previews;
- execution success/error;
- console/log output;
- RAM/VRAM measurements at Workflow boundaries.

The orchestration layer must not become a black box.

## Persistence

The intended storage split is:

- **GitHub** — source code, documentation and releases;
- **Google Drive** — persistent project/run data, Context assets and Checkpoints;
- **Colab /content** — fast temporary scratch space.

Persistence is not required for the first memory-boundary proof of concept.

## Non-goals for the first implementation

Do not build yet:

- branching/DAG execution;
- loops or conditions;
- variable history/provenance;
- sophisticated Context versioning;
- complex visual Context editor;
- automatic public ComfyUI Manager publication.
