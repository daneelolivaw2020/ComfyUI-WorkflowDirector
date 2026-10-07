# Phase 0 Lab — Installation and Instrumentation

## Question being tested

Can a clean installation of the current stable ComfyUI load
ComfyUI-WorkflowDirector and expose trustworthy memory instrumentation without
changing model-management behaviour?

## Version rule

Use the latest official stable ComfyUI release tag when the lab begins and
record the exact version.

See COMPATIBILITY.md for the currently audited stable release.

Do not use the moving master branch as the laboratory baseline.

## Minimal environment

Install only:

1. current stable ComfyUI;
2. ComfyUI-WorkflowDirector.

Do not yet install GGUF, unload/cleanup extensions, rgthree, Crystools, KJNodes
or the production custom-node bundle.

Do not copy the old notebook's memory flags into this clean baseline. Start with
ComfyUI defaults.

## Installation

Once this repository is public:

    cd /content/ComfyUI/custom_nodes
    git clone https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector.git

During development the repository itself may track main. ComfyUI, however,
should be checked out at an official stable release tag for a reproducible test
cycle.

## Smoke test

After ComfyUI starts:

1. Confirm the console does not report an import error for WorkflowDirector.
2. Open /workflowdirector/health relative to the running ComfyUI URL.
3. Verify that the response reports both the WorkflowDirector version and the
   actual ComfyUI runtime version.
4. Call /workflowdirector/memory once as a CUDA warm-up measurement.
5. Use a second reading as the baseline.
6. Add **WorkflowDirector · Test Marker** in ComfyUI.
7. Queue it twice without changing its inputs.

Expected behaviour:

- the V3 custom node loads normally;
- the marker executes both times instead of being reused from cache;
- both runs print fresh RAM/VRAM metrics;
- memory measurements do not unload, move or mutate models.

The first CUDA query is not used as the baseline because initializing/querying
the CUDA context can itself alter memory usage.

## Important limitation

Phase 0 performs **no memory release** and no orchestration.

That is deliberate. Phase 1 adds two-job sequencing. Phase 2 then observes what
the current ComfyUI release naturally does to memory before WorkflowDirector
adds any cleanup mechanism.
