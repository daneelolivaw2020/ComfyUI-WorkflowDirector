# Phase 0 Lab — Installation and Instrumentation

This lab is intentionally smaller than the final product.

## Question being tested

Can a clean ComfyUI installation load ComfyUI-WorkflowDirector and expose reliable process/GPU memory measurements without adding model-management behavior of its own?

## Minimal environment

For the first run install only:

1. the pinned ComfyUI build under test;
2. ComfyUI-WorkflowDirector.

Do **not** install GGUF, unload/cleanup nodes, RAM cache extensions, rgthree, Crystools, or the user's production custom-node bundle yet.

Those are added only when the corresponding validation phase requires them.

## Installation

Once this repository is public:

```bash
cd /content/ComfyUI/custom_nodes
git clone https://github.com/daneelolivaw2020/ComfyUI-WorkflowDirector.git
```

Restart ComfyUI after cloning.

During active development it is acceptable to pull `main`. Once a known-good version exists, the Colab notebook should check out a pinned tag instead.

## Smoke test

After ComfyUI starts:

1. Confirm the console does not report an import error for WorkflowDirector.
2. Open:
   - `/workflowdirector/health`
   - `/workflowdirector/memory`
   relative to the running ComfyUI URL.
3. In ComfyUI add **WorkflowDirector · Test Marker**.
4. Queue it.

Expected console output resembles:

```text
[WorkflowDirector] WorkflowDirector test marker | RAM RSS=... GiB | VRAM allocated=... GiB | reserved=... GiB | free=... GiB / ... GiB
```

The exact values are machine-dependent.

## Important limitation

Phase 0 performs **no memory release**. It is read-only instrumentation.

That is deliberate. The Memory Barrier will be introduced only after we can record trustworthy before/peak/after measurements and execute two separate prompts in a controlled minimal environment.
