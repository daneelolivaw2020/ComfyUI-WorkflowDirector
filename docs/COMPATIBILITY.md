# Compatibility Policy

## Target

WorkflowDirector targets the **latest stable ComfyUI release** during early
development.

"Latest" means the most recent official stable release tag, not the repository's
moving master branch.

Current audited target on 2026-10-07:

    ComfyUI v0.39.0

## Why

The project is new. Carrying compatibility code for old ComfyUI releases before
the architecture is proven would add complexity without helping the primary
goal.

The older environment where the original GGUF memory failure was observed is
historical context only and is not a support target.

## Upgrade rule

When a new stable ComfyUI release appears:

1. read its release notes;
2. review the integration points used by WorkflowDirector;
3. run the two-pass code review;
4. run the minimal lab;
5. run the two-workflow boundary test;
6. run the heavy-model regression test when its dependencies support the new
   ComfyUI release;
7. only then mark the new release as the audited target.

The test log must record the exact ComfyUI version even though the product policy
is to follow latest stable.

## API preference

Prefer public/current ComfyUI interfaces over internal implementation details.

Current preferred integration points include:

- V3 custom-node API through `comfy_api.latest`;
- normal `/prompt` submission;
- WebSocket execution/progress events for live UI feedback;
- the native Jobs API for durable job state.

Internal structures such as PromptQueue tuples, PromptExecutor internals,
current_loaded_models and LoadedModel are diagnostic implementation details.
They must not become the core WorkflowDirector contract.

## Current audit notes for v0.39.0

Verified against the v0.39.0 source:

- V3 `ComfyExtension` / `io.ComfyNode` registration is available;
- custom routes through `PromptServer.instance.routes` are available;
- `/api/jobs/{job_id}` exposes pending, in_progress, completed, failed and
  cancelled states;
- a job enters history only after `PromptExecutor.execute()` returns;
- `execution_success` is emitted before the PromptExecutor finalizer finishes,
  so it is useful for UI feedback but is not by itself the commit/memory-barrier
  signal;
- cgroup-aware RAM helpers remain available;
- `psutil` remains a ComfyUI requirement.
