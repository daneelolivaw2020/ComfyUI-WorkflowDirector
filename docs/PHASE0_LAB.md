# Phase 0 Lab — Installation and Instrumentation

This lab is intentionally smaller than the final product.

## Question being tested

Can a clean ComfyUI installation load ComfyUI-WorkflowDirector and expose reliable process/GPU memory measurements without adding model-management behavior of its own?

## Minimal environment

For the first run install only:

1. ComfyUI v0.37.0;
2. ComfyUI-WorkflowDirector.

Do **not** install GGUF, unload/cleanup nodes, RAM cache extensions, rgthree, Crystools, or the production custom-node bundle yet.

Those are added only when the corresponding validation phase requires them.

## Installation

Once this repository is public:

    cd /content/ComfyUI/custom_nodes
    git clone https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector.git

Restart ComfyUI after cloning.

During active development it is acceptable to pull main. Once a known-good version exists, the Colab notebook should check out a pinned tag instead.

## Smoke test

After ComfyUI starts:

1. Confirm the console does not report an import error for WorkflowDirector.
2. Open these routes relative to the running ComfyUI URL:
   - /workflowdirector/health
   - /workflowdirector/memory
   - /workflowdirector/status
3. Call /workflowdirector/memory once as a CUDA warm-up measurement.
4. Use a second reading as the baseline. The first CUDA query may initialize a CUDA context and slightly change memory usage.
5. In ComfyUI add **WorkflowDirector · Test Marker**.
6. Queue it twice without changing its inputs.

Expected behavior:

- the marker executes both times rather than being served from cache;
- both runs print fresh RAM/VRAM metrics;
- /workflowdirector/status reports worker_idle=true when no prompt is executing;
- queue_empty is true only when there is neither a running nor a pending prompt.

Expected console output resembles:

    [WorkflowDirector] WorkflowDirector test marker | RAM RSS=... GiB | system available=... / ... GiB | VRAM torch allocated=... GiB | reserved=... GiB | device used=... GiB | free=... / ... GiB

The exact values are machine-dependent.

## Important limitation

Phase 0 performs **no memory release**. It is read-only instrumentation.

That is deliberate. The Memory Barrier will be introduced only after we can record trustworthy before/peak/after measurements and execute two separate prompts in a controlled minimal environment.
