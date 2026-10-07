# Architecture

## Design goal

WorkflowDirector should feel like a native visual layer on top of ComfyUI rather than a separate script-driven system.

The intended user experience is eventually:

```text
[ MASTER ] [ Workflow 1 ] [ Workflow 2 ] [ Workflow 3 ]
```

Each individual Workflow remains a normal ComfyUI document. The Master coordinates them at a higher level.

## Responsibilities

### Master

The Master defines high-level execution order.

Initial version:

```text
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
```

Master connections primarily represent execution dependency, not every piece of data passed between workflows.

### Workflow

A Workflow:

- is a normal ComfyUI workflow;
- can be opened and tested independently;
- can read selected values from Context;
- can publish new or replacement values to Context;
- must finish as its own top-level ComfyUI execution.

### Context

Context is deliberately schema-light.

Conceptually:

```text
KEY -> TYPE -> VALUE
```

Key names are arbitrary. The system must not hard-code concepts such as `current_image`, `current_prompt`, or `current_latent`.

Initial cross-workflow data types will likely be:

- STRING
- IMAGE
- LATENT

Other types can be added later without changing the core model.

### Checkpoint

A Checkpoint is an explicit saved snapshot of Context.

Checkpointing is intentionally simpler than full history/versioning. History, provenance, branching and undo are outside the initial scope.

### Memory Barrier

The Memory Barrier is the architectural reason for separate Workflow executions.

It occurs only after the previous prompt has fully completed.

Conceptually:

```text
Workflow N
   |
execution_success / real prompt completion
   |
Memory Barrier
   |
measure RAM/VRAM
   |
release stale model references / caches safely
   |
measure again
   |
Workflow N+1
```

The system must not depend on an unload node running inside the same prompt.

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

- **GitHub** — source code, documentation, releases.
- **Google Drive** — persistent project/run data, Context assets and Checkpoints.
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
