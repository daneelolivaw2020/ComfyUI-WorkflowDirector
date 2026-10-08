# Context MVP — transactional CPU-only handoff (development)

This change is a source-code implementation and **not yet a T4/ComfyUI runtime acceptance**.
It builds on the successful A→B memory-boundary experiments without
changing \`--cache-none\`, the native Jobs API, the top-level queueing
protocol, or the memory observer.

## Architecture

\`\`\`text
DirectorRunService.start(plan)
  ContextRegistry.start_run(run_id)
    |
    DirectorEngine.begin_step(A job_id)
    Native Comfy job A
      WorkflowDirectorContextPutImage("portrait", image)
      -> stage detached CPU copy in StepPatch[A]
    Jobs API = completed
    ContextRegistry.commit_step(A job_id)  <-- atomic publish
    Memory boundary observation
    |
    DirectorEngine.begin_step(B job_id)
    Native Comfy job B
      WorkflowDirectorContextGetImage("portrait")
      -> independent detached CPU copy
    Jobs API = completed
    ContextRegistry.commit_step(B job_id)
    Memory boundary observation
    |
  ContextRegistry.end_run(run_id) <-- release all Context references
\`\`\`

No Context node passes a model patcher, CLIP, VAE or GPU-resident value
across top-level jobs. Values are identified by user-chosen keys, not fixed
variables. Each native prompt gets its identity from Comfy's
\`comfy_execution.utils.get_executing_context().prompt_id\` on the actual
prompt worker thread. A manually queued prompt has no registered Director
transaction and cannot read/write run Context. A `Context Put` in
a manually queued workflow is an explicit pass-through only (logged; nothing
is published). A `Context Get` still needs a previously committed value from
an active Director run and therefore fails outside one. This manual-Get
limitation must be addressed before claiming full standalone reproducibility
for a downstream, Context-dependent workflow.

## Node types

| V3 node id | Inputs | Outputs | Role |
| --- | --- | --- | --- |
| \`WorkflowDirectorContextPutString\` | key, STRING value | STRING | Stage STRING |
| \`WorkflowDirectorContextGetString\` | key | STRING | Read prior committed STRING |
| \`WorkflowDirectorContextPutImage\` | key, IMAGE value | IMAGE | Stage CPU IMAGE |
| \`WorkflowDirectorContextGetImage\` | key | IMAGE | Read prior committed CPU IMAGE |
| \`WorkflowDirectorContextPutLatent\` | key, LATENT value | LATENT | Stage CPU LATENT |
| \`WorkflowDirectorContextGetLatent\` | key | LATENT | Read prior committed CPU LATENT |

Put nodes are output nodes and have a pass-through output, so they are
executed even without other consumers. Output caching is disabled for
all six Context nodes through \`fingerprint_inputs\`.

**LATENT metadata accepted in this first slice**: \`samples\` (required),
\`noise_mask\` (optional tensor), \`batch_index\` (optional integer list),
and \`type\` (optional short string). Unknown fields are explicitly rejected
rather than silently storing model objects or accidentally dropping data.

## Transaction guarantees

- One active Director run and one active native step at a time.
- Writes remain invisible until native job state **completed**.
- Duplicate writes to one key in a single step are an error.
- A subsequent step may replace an already committed key.
- An errored, cancelled, uncertain or interrupted step cannot commit.
- The session is destroyed on every run exit; no global payload cache.
- Get returns a *fresh copy* of CPU data so consumers cannot mutate
  committed values.
- Keys are arbitrary Unicode strings up to 128 characters (no controls or
  padding); initial logical types are STRING, IMAGE, LATENT only.

## RAM safety and current limitations

The first slice is intentionally **CPU RAM only**. It does not yet implement
scratch spill, checkpoints, Google Drive persistence, or durable backend
restart recovery.

Default bounds:
- maximum 128 MiB per value/tensor;
- maximum 256 MiB of committed-plus-staged logical Context per run.

The codec checks size before transferring GPU tensors to CPU, and always
creates a detached CPU copy. These limits suit small to moderate image/latent
hand-offs for initial testing; larger values fail explicitly. The exact
peak allocation can still include a temporary duplicate during Put/Get and
is not reflected in the Context accounting. This will be instrumented later.

The Context registry does not persist after a finished run. A user wishing
to reuse the output in another Master run will eventually need a Checkpoint.

## Tests

\`\`\`bash
python -m unittest discover -s tests -v
node --test tests/lab_ui.test.cjs
\`\`\`

Tests cover staged visibility, commit, abort, duplicate writers, unsupported
model types, key validation, entry/total budgets, CPU clone semantics via a
Torch stand-in, and the DirectorEngine→DirectorRunService lifecycle including
job success/failure.

**Not tested by CI**: actual Comfy V3 node registration and hidden native
prompt context, CUDA CPU transfer, allocation peaks, latents used by Klein,
and graphical linkage on Colab. Treat these as a runtime acceptance gate
before merging into \`main\`.

## Planned Colab acceptance (do not run until ready)

1. Use the audited ComfyUI 0.39 / frontend 1.53.10 / T4 / \`--cache-none\`.
2. In A, wire \`VAEDecode.image\` → \`Context Put · IMAGE\`
   with key \`portrait\`; keep \`SaveImage\`.
3. In B, wire \`Context Get · IMAGE\` with key \`portrait\` to
   \`SaveImage\` for a light functional handoff. Run A→B via Director.
4. Verify that B reproduces A's pixel data and not a stale captured image.
5. Repeat for LATENT from A's sampler into B's consumer, and STRING.
6. Force a failed A and verify that B is not submitted and no patch is
   committed.
7. Record RSS/PSS, GPU memory after both steps and peak during each job.

Do not add manual \`/free\`, unload nodes, or destructive cleanup.
