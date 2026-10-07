# Comfy Adapter Contract

The Director core must not know ComfyUI HTTP paths, queue tuples or server
internals. All Comfy-specific behaviour is isolated behind the adapter.

## Current integration strategy

For the audited stable ComfyUI release, the backend Director should talk to the
same local Comfy server through loopback HTTP rather than duplicate the
implementation of /prompt inside WorkflowDirector.

That preserves ComfyUI's own:

- prompt validation;
- on-prompt handlers;
- node replacement;
- queue numbering;
- native history/jobs behaviour;
- error response shape.

The browser/tunnel is not on this internal control path.

## Submit

Use the native prompt endpoint with a WorkflowDirector-generated UUID supplied
as prompt_id before the request is sent.

The body must preserve normal Comfy frontend semantics:

    {
      "client_id": "<browser session id when available>",
      "prompt_id": "<preassigned WorkflowDirector job UUID>",
      "prompt": <prepared API prompt>,
      "extra_data": {
        "comfy_usage_source": "workflowdirector",
        "extra_pnginfo": {
          "workflow": <frozen visual workflow snapshot>
        }
      }
    }

Authentication/API-key fields, if ever required by a workflow, are runtime
credentials and must not be frozen into the RunPlan.

## Why keep the visual workflow snapshot

Normal Comfy queueing sends both:

- output/API prompt;
- visual workflow JSON in extra_pnginfo.

WorkflowDirector must preserve that relationship so history, metadata and saved
outputs remain associated with the workflow that actually produced them.

The user never maintains a separate API JSON file. Both representations are
generated/frozen internally from the visual workflow when the RunPlan is
prepared.

## client_id

The current Comfy executor routes execution_start/executing/executed and related
messages using the client_id stored in prompt extra_data.

The client_id is **not** part of the immutable RunPlan. It is ephemeral runtime
routing state supplied when a run starts.

The backend run must not depend on that browser remaining connected. If the
browser disappears, sequencing continues. A future Director service can update
the routing client id after frontend reconnection without changing the prepared
workflow snapshots.

## Job lookup

Use the native endpoint:

    GET /api/jobs/{job_id}

Map:

- HTTP 404 -> UNKNOWN;
- pending -> PENDING;
- in_progress -> IN_PROGRESS;
- completed -> COMPLETED;
- failed -> FAILED;
- cancelled -> CANCELLED.

Malformed responses are adapter errors, not UNKNOWN.

## Transport errors

Submission transport failure is special because the prompt may already have
been accepted.

The adapter raises SubmissionTransportError when acknowledgement is ambiguous.
The Director then queries the preassigned job UUID and never blindly resubmits.

Transient lookup connectivity failures raise AdapterTransportError and may be
retried until the Director's monotonic timeout expires. Job waits are bounded by
elapsed time, not by a fixed poll count, so changing poll frequency does not
silently change the maximum Workflow duration.

## Memory endpoint

WorkflowDirector's own /workflowdirector/memory endpoint remains read-only
instrumentation.

The memory barrier policy is separate from the execution adapter. Native /free
experiments belong in the boundary observer, not in submit/get-job logic.

## Future compatibility

If ComfyUI changes its native submission/jobs interfaces, only this adapter
layer should change. RunPlan, DirectorEngine, Context and Master semantics must
remain unaffected.
