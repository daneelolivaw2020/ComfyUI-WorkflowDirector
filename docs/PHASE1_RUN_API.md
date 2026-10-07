# Phase 1 Run API

This is an internal integration surface for the WorkflowDirector frontend and
laboratory. The user is not expected to create or maintain API prompt JSON by
hand.

## Purpose

Phase 1 proves only:

    prepared Workflow A
        |
    native Comfy job
        |
    terminal completed
        |
    prepared Workflow B
        |
    native Comfy job

The current runtime reports:

    boundary_mode = noop-phase1

This is intentional. Phase 1 does not claim that model memory has been released.

## Start a run

Preferred API alias:

    POST /api/workflowdirector/runs

The custom route also exists without the /api prefix because current ComfyUI
registers both forms.

Request body:

    {
      "run_id": "<optional UUID>",
      "client_id": "<optional current Comfy browser session id>",
      "steps": [
        {
          "step_id": "A",
          "workflow_id": "<stable workflow id>",
          "name": "Workflow A",
          "prompt": { ... transient executable prompt ... },
          "workflow": { ... frozen visual workflow snapshot ... }
        },
        {
          "step_id": "B",
          "workflow_id": "<stable workflow id>",
          "name": "Workflow B",
          "prompt": { ... },
          "workflow": { ... }
        }
      ]
    }

The frontend will generate both prompt and workflow representations from the
normal visual Comfy workflow. They are not user-managed files.

If run_id is omitted, WorkflowDirector creates it before any Comfy prompt is
submitted.

Response status 202 returns the run id and current RunRecord.

## Read run state

    GET /api/workflowdirector/runs/{run_id}

Returns the live service-owned RunRecord plus whether it is the currently active
WorkflowDirector run.

The same RunRecord object is mutated by DirectorEngine while the run progresses,
which allows the future Master UI to poll/recover state without owning the
execution loop.

## Current safety properties

- only one WorkflowDirector Master run may be active at a time;
- every Workflow attempt receives a deterministic preassigned UUID;
- the native Comfy Jobs API is authoritative for terminal state;
- failed/cancelled jobs stop the sequence;
- ambiguous submission acknowledgements are recovered by UUID lookup, never
  blind resubmission;
- before each Workflow submit, WorkflowDirector queries native active jobs and
  refuses to submit if Comfy already has pending/in-progress work;
- visual workflow metadata is submitted together with the executable prompt;
- browser client_id is runtime routing state, not immutable RunPlan state.

## Current limitations

Phase 1 still does not provide:

- Context transfer;
- Drive persistence;
- checkpoint/resume;
- continuous queue lease/monitoring during a long memory observation window;
- visual Master UI;
- automatic workflow compilation from tabs;
- memory release or cleanup.

For the Phase 1 laboratory, Auto Queue should be disabled and the user should
not manually queue unrelated Comfy jobs while a Director run is active.

Phase 2 connects the observation boundary and memory measurements.
