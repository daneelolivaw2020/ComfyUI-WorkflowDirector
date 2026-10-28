# Real-environment test gate — 2026-10-07

This gate is intentionally narrower than the final WorkflowDirector product.

## Audited target

- Google Colab Free Tier
- NVIDIA T4
- standard-memory runtime
- ComfyUI v0.39.0
- comfyui-frontend-package 1.53.10
- WorkflowDirector current development branch
- phase-2 boundary mode: `observe-phase2-nondestructive`

## Code-review result before the lab

The backend control path is suitable for the first real test:

- the Director is not a Comfy prompt node;
- one prepared Workflow is submitted at a time;
- each attempt receives a deterministic UUID;
- native Jobs API terminal state is the execution boundary;
- the successor is not submitted until the observation boundary finishes;
- active foreign jobs are treated as contamination and fail closed;
- the boundary is read-only and does not call `/free`, `unload_all_models()`,
  allocator reset, or executor-cache reset;
- baseline and post-job observations separate process RSS, system RAM,
  PyTorch allocated/reserved VRAM and device-global VRAM;
- recent core CI is green on the supported Python test matrix.

No destructive memory-management code is introduced for this lab.

## Known limitation accepted for this lab

The browser Lab captures the current document with `app.graphToPrompt()`.

Normal Comfy queueing may invoke pre-queue callbacks before compilation. The
current Lab therefore does not yet claim full semantic equivalence for custom
nodes that mutate their prompt immediately before queueing.

Consequences:

1. smoke workflows use only `WorkflowDirectorTestMarker`;
2. a heavy workflow must first be proven to run normally by itself;
3. if a captured GGUF/Power-LoRA workflow differs from normal queue execution,
   stop and fix the frontend compilation adapter rather than changing memory
   policy.

This limitation is not a reason to weaken the top-level job boundary.

## Security correction

A historical Colab notebook used during the v0.37 investigation contained a
plaintext third-party token. The replacement notebook contains no embedded
credentials. Private GitHub access is read from Colab Secret `GITHUB_TOKEN`.

Any historical token that was embedded in an old notebook should be rotated or
revoked before that old notebook is reused or shared.

## Test order

1. clean v0.39.0 + WorkflowDirector only;
2. smoke A -> B;
3. real A-only with normal Comfy cache;
4. same A-only with only `--cache-none` changed;
5. real A -> B with the known-working GGUF / Power-LoRA workflows;
6. only after the boundary survives, implement/test cross-workflow Context.

## Pass gate

The first real gate passes only if:

- A and B are different native jobs;
- A is terminal before B is submitted;
- no unrelated jobs contaminate the boundary;
- Comfy/Colab remains alive;
- memory observations are present for both steps;
- the heavy A -> B case can be repeated without a runtime/kernel restart.

The observation data must not be interpreted as proof of model-object
destruction solely from one VRAM metric.
