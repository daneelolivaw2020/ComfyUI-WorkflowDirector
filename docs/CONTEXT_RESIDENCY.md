# Context Residency

Context defines **what survives between Workflows**. It does not require every
surviving value to be serialized to disk at every boundary.

## Logical Context vs physical residency

Each Context entry has a logical identity:

    key -> type -> value

and an internal physical residency chosen by WorkflowDirector.

Initial logical types:

- STRING
- IMAGE
- LATENT

Initial residency modes:

- **RAM** — hot value retained in CPU memory for immediate reuse;
- **SCRATCH** — serialized under local runtime scratch, normally /content;
- **DURABLE** — serialized to persistent storage when persistence/checkpointing
  is required.

The same logical Context key may move between these residency modes without the
consumer Workflow changing how it references the key.

## Default MVP policy

- STRING: keep in RAM.
- IMAGE: keep in CPU RAM when reasonably small and useful to a near-term
  consumer.
- LATENT: keep in CPU RAM when reasonably small and useful to a near-term
  consumer.
- spill IMAGE/LATENT to /content when Context RAM pressure requires it.
- serialize to durable storage only for checkpoints/persistence requirements.

Current ComfyUI normally places intermediate tensors on CPU unless gpu-only mode
is used. WorkflowDirector must nevertheless verify the actual tensor device
before accepting an IMAGE/LATENT into hot Context. A hot Context entry must not
silently pin large tensors in T4 VRAM.

## Forbidden persistent Context types

Do not persist live execution objects such as:

- MODEL
- CLIP
- VAE
- CONTROL_NET
- GUIDER
- SAMPLER
- model patchers or equivalent model-management objects.

Those objects belong to one Workflow execution and must remain releasable at the
memory boundary.

## Transaction model

Context writes produced by a Workflow are staged in a StepPatch.

A StepPatch becomes committed Context only after the Workflow job reaches a
successful terminal state.

Failed, cancelled or uncertain attempts commit nothing.

For the MVP, a Workflow may not publish two writes to the same Context key in
one attempt. Duplicate writers are rejected during validation.

## Future AUTO policy

The architecture should allow an AUTO residency policy that considers:

- value size;
- current system RAM headroom;
- distance to the next consumer Workflow;
- number of remaining consumers;
- whether the value must survive runtime loss;
- cost of serialization/deserialization.

This optimization is deliberately not required for the first memory-boundary
proof.
