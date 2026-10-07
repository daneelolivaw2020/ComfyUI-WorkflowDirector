# Architecture Review — 2026-10-07

This review precedes implementation of the Runner, Context, RunRecord and lab
notebook. It intentionally changes architecture where the earlier reasoning was
too coupled to prompt execution or insufficiently crash-safe.

## Reviewed target

- Google Colab Free Tier
- NVIDIA T4
- standard-memory runtime
- current audited stable ComfyUI
- exact frontend package required by that ComfyUI release

The exact audited versions remain in COMPATIBILITY.md.

## Review A — structural correctness

### 1. The Director must not be a Comfy prompt node

A node that submits Workflow A and waits for Workflow B would occupy the same
prompt worker required to execute those jobs. The orchestration engine therefore
must live outside prompt execution.

### 2. Split the system into three layers

Frontend extension:
- Master visual document and workflow references
- Run preparation / workflow snapshotting
- tabs, Follow Execution, Context panel and Master Console
- live WebSocket observation

WorkflowDirector backend service:
- run state machine
- one-job-at-a-time sequencing
- transactional Context commit
- memory observations/barrier policy
- durable run state
- Comfy backend adapter

Normal Comfy prompt worker:
- executes each Workflow job unchanged

The backend service may run in the Comfy process, but it is not a node and must
not run inside PromptExecutor.

### 3. Master is a control document, not an executable Comfy prompt

The Master can use the Comfy canvas and workflow-tab experience, but its graph
represents control flow. It must never be flattened into one prompt.

Master Workflow blocks reference actual workflows by stable workflow UUID.
Names/paths are display metadata and must not be the primary identity because
workflows can be renamed.

### 4. Each run uses immutable workflow snapshots

At execution time WorkflowDirector freezes the workflow state used by a step.
The executable API prompt is generated internally/transiently from the visual
workflow. The user never maintains API JSON.

This prevents edits made while a run is active from silently changing an
already-planned step. Retrying an edited failed Workflow creates a new snapshot
for that attempt.

### 5. Compilation must preserve normal Comfy semantics

Current Comfy frontend queueing runs pre-queue widget callbacks before
graphToPrompt. WorkflowDirector must not create a second, subtly different
compiler.

For the initial implementation, preparing a workflow may temporarily activate
the real workflow and reuse the current Comfy frontend semantics. Off-screen
compilation is a later optimization only after it is proven equivalent.

### 6. Execution and memory boundaries are separate

Jobs API terminal state is the execution boundary.

Memory quiescence/release is a separate barrier phase.

The next Workflow is never pre-queued while the barrier is being evaluated.

### 7. Do not use the native /free endpoint as the first safe barrier

A source review of ComfyUI v0.39.0 found an important coupling.

The /free route only sets the free_memory flag when free_memory=true. In the
prompt worker, model unloading is then decided with:

    flags.get("unload_models", free_memory)

Therefore a free_memory=true request causes unload_all_models() when no explicit
unload_models flag is present. Sending unload_models=false in the HTTP body does
not avoid this because the route does not store a false flag.

This puts native /free in the same broad failure class as the aggressive unload
path that originally killed the Colab runtime.

WorkflowDirector therefore does **not** use /free in the initial safe barrier.

The safer progression is:

1. current defaults, observe only;
2. cache-isolation run with --cache-none, observe only;
3. if still necessary, diagnose remaining references;
4. design a narrowly targeted post-job cleanup that does not route through
   unload_all_models().

### 8. Context survival is explicit; residency is independent

Persistent Context must never keep MODEL, CLIP, VAE or other model-management
objects.

IMAGE and LATENT are different: they are legitimate Context values and may
survive between Workflow jobs in CPU RAM when that is efficient. They may also
spill to /content scratch or become durable serialized assets. The logical
Context key does not change when residency changes.

WorkflowDirector must verify that a hot Context tensor is not unintentionally
resident in T4 VRAM.

A Context Put stages a StepPatch during prompt execution. Persistent Context
changes only after the job is confirmed successful.

### 9. Context writes are transactional and deterministic

A failed/cancelled job commits nothing.

For the MVP, two Context Put operations in the same Workflow may not write the
same key. Duplicate writes are rejected because Comfy graph execution does not
provide a meaningful visual "last writer wins" rule.

### 10. Colab storage roles are distinct without changing Comfy model paths

Google Drive:
- persistent run state, durable Context assets and Checkpoints when configured;
- may also be part of the user's existing model-storage setup.

 /content:
- fast runtime scratch;
- temporary spilled Context assets;
- the normal Comfy installation/model tree when Comfy is installed there.

WorkflowDirector does not introduce its own model directory and does not require
moving GGUF files for the first baseline. Keep the user's normal Comfy model
lookup unchanged. A local-copy-vs-mounted-Drive comparison is a later controlled
diagnostic only if storage/mmap behaviour becomes relevant.

## Review B — adversarial failure analysis

### Browser closes or disconnects

The final run must not depend on a browser JavaScript loop staying alive.
Therefore the backend service owns the run state machine after a prepared RunPlan
is started. The frontend is controller/observer.

### Comfy backend dies

Run state must be persisted after meaningful transitions. On restart, the
Director reads the last durable state rather than assuming success.

If the entire backend/runtime died while a job was running, completion cannot be
trusted merely because scratch output exists. The step becomes uncertain and is
rerun from the last committed Context/Checkpoint unless there is durable proof
of successful commit.

### Submission succeeds but acknowledgement is lost

ComfyUI accepts a client-supplied UUID prompt_id. WorkflowDirector should create
and persist the intended job id before submission.

After reconnect/recovery it queries that id before deciding whether submission
must be retried. It must never blindly resubmit an unknown/ambiguous step.

### User manually queues another job

A Director memory barrier is invalid if unrelated jobs run between A and B.

During an active Master run, WorkflowDirector either owns the queue window or
pauses when it detects an unexpected job. The MVP should fail/pause safely rather
than silently interleave jobs.

Auto-queue is therefore also a conflict to detect/disable for the run.

### Same model in B

A -> B with the same Klein base can prove practical safe continuation but may be
reuse, not release. A-only observations and cache-isolation tests remain
separate from the practical transition test.

### Default Comfy cache

Default RAM-pressure caching intentionally keeps useful outputs, including model
patcher outputs, until pressure requires eviction. Retention under default cache
is not automatically a leak.

A strict release experiment first uses --cache-none as the controlled cache
variable. Native /free is excluded from the initial safe path because current
v0.39.0 couples free_memory to unload_all_models().

### Memory settling

Job completed and memory settled are different events.

The barrier records immediate and settled observations. It must not use a fixed
sleep as the product contract; fixed timing is only a laboratory aid. The final
policy should use observable state/measurements plus a timeout.

### Frontend compatibility

The frontend is versioned independently from the ComfyUI backend. WorkflowDirector
must audit the frontend package required by each supported ComfyUI release.

All access to workflowStore, workflowService, graphToPrompt, tabs and frontend
events belongs behind a small frontend adapter.

### Console

Current frontend receives native Comfy log messages over WebSocket. Master
Console should consume that native stream and merge WorkflowDirector events,
rather than depend on tailing a Colab logfile.

## Revised core objects

MasterDefinition:
visual control graph and stable workflow references.

RunPlan:
immutable Master/workflow snapshots and transient executable prompts for a run.

RunState:
current step/attempt/job id/status and commit/barrier state.

ContextManifest:
committed key -> typed lightweight value/asset reference mapping.

StepPatch:
uncommitted writes produced by exactly one Workflow attempt.

Checkpoint:
explicit reference to one committed Context snapshot.

MemoryObservation:
timestamped RAM/VRAM measurements attached to a boundary.

## Implementation order after this review

Do not implement the full feature set at once.

The next code slice should contain only:
- Comfy backend adapter abstraction
- minimal backend Director state machine for two trivial prepared prompts
- deterministic job ids and terminal-state handling
- memory observations
- simulated tests for success/failure/reconnect

Context assets, Drive persistence, visual Master and heavy GGUF logic remain
outside that first code slice.

The first runtime acceptance remains Colab Free + T4.
