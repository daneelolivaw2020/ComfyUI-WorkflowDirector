# First Colab T4 Test

This is the first runtime validation procedure for WorkflowDirector.

Mandatory environment:

    Google Colab Free Tier
    NVIDIA T4
    standard-memory runtime
    current audited stable ComfyUI release

The repository may still be private during development. Once it is public, the
normal laboratory install can use a plain git clone.

## Test discipline

For all tests below:

- disable Auto Queue;
- do not manually queue unrelated Comfy workflows while a Director run is active;
- use fixed seeds;
- avoid nodes whose behaviour depends on beforeQueued callbacks for this first
  laboratory build;
- use no unload/free-memory custom nodes;
- do not call Comfy /free;
- start with Comfy's normal memory defaults;
- keep the existing normal model paths.

The Workflow Director Lab bottom panel stores captured A/B snapshots only in the
current browser tab. It does not modify the saved workflow files.

## Smoke test — separate top-level jobs

Before using a heavy model, verify the control path with lightweight workflows.

1. Open a trivial normal Comfy workflow.
2. Open the Workflow Director Lab bottom panel.
3. Capture current as A.
4. Switch to another trivial workflow and capture current as B.
5. Run A -> B.
6. Confirm the run reaches completed.
7. Confirm the RunRecord contains two different deterministic job ids and A
   reaches completed before B is submitted.

This proves sequencing only.

## Real test A — one actual image, observe memory

Workflow A must genuinely exercise the target model path. A loader-only workflow
is not sufficient.

A should contain the same known-working generation path required by the target
case:

    GGUF diffusion model loader
        +
    GGUF text encoder loader
        +
    fixed prompt
        +
    VAE loader
        +
    sampler
        +
    VAE decode
        +
    preview/save image

For the target regression use Klein Q6, the intended Qwen encoder and the
known-working VAE/sampling path.

There must be no unload node in A.

Procedure:

1. Restart into a clean Colab/Comfy session if the preceding smoke test loaded
   anything material.
2. Verify Workflow A runs normally by itself once if needed to validate the
   workflow construction. If this warm-up would invalidate the memory baseline,
   restart Comfy before the actual measurement run.
3. Open Workflow Director Lab.
4. Capture A.
5. Click Run A only.
6. Do not queue anything else.
7. Wait for the Director run to reach completed.
8. Record the displayed table.

The table contains:

    BASELINE
    POST_IMMEDIATE
    POST_WINDOW_SAMPLE_xxx
    POST_WINDOW_END

and keeps these metrics separate:

    process RSS
    system RAM available
    PyTorch allocated VRAM
    PyTorch reserved VRAM
    device-global used VRAM
    diagnostic loaded-model entry count

This run answers:

> What memory state remains after one real top-level Workflow under current
> Comfy defaults?

It does not automatically answer:

> Was the model object destroyed?

## Real test B — cache-isolation A-only

If default Comfy caching retains substantial state, repeat the exact same A-only
experiment with one controlled change:

    --cache-none

Change nothing else.

Do not simultaneously change model quantization, model path, pinned-memory
flags, async offload, DynamicVRAM or workflow structure.

Compare the complete memory series against the default-cache run.

This asks whether executor output caching was the strong-reference source.

## Real test C — practical A -> B transition

Only after A-only observations are captured:

1. Prepare Workflow A with fixed prompt/seed and LoRA stack A.
2. Prepare Workflow B as a separate normal Comfy workflow.
3. B may initially use the same Klein Q6, Qwen and VAE path but a different
   prompt and LoRA stack B.
4. Capture A.
5. Switch tabs and capture B.
6. Run A -> B.
7. Confirm:
   - A produces the intended image;
   - A reaches native completed;
   - its memory observation boundary finishes;
   - B is submitted only afterward;
   - B produces its intended image;
   - the Colab kernel does not restart;
   - system RAM does not enter a dangerous exhaustion pattern.

Success here proves practical sequential execution/reuse safety. It does not by
itself prove that Klein was unloaded between A and B.

## Stronger switching test

If the original Klein A -> B use case works, a later test may use a genuinely
different heavy model in B. That is a stronger model-switching proof, but it is
not required before solving the original use case.

## Failure handling

If the kernel dies:

- do not infer the last memory state from missing logs;
- note the last visible observation/job event;
- restart the runtime;
- preserve the exact Comfy tag, WorkflowDirector commit and launch flags in the
  test record;
- reproduce with one variable changed at a time.

If WorkflowDirector reports QUEUE_INTERFERENCE or QUEUE_NOT_EXCLUSIVE, treat the
run as contaminated and repeat it rather than interpreting its memory numbers.

## What is deliberately not tested yet

This first laboratory does not validate:

- Context IMAGE/LATENT transfer;
- checkpoints;
- Drive persistence;
- automatic retry;
- final Master visual graph;
- automatic beforeQueued-equivalent workflow compilation;
- destructive model cleanup.

Those remain downstream of the execution/memory proof.
