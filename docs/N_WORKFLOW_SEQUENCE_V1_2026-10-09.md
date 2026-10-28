# WorkflowDirector: ordered N-workflow UI (experimental V1)

Implemented on branch `feature/universal-context-nodes`. Reuses the existing
`POST /workflowdirector/runs` backend and `RunPlan.steps`; neither the
ComfyUI prompt executor nor the universal Context transport is modified.

## UI usage in ComfyUI

1. Open as many ordinary workflows as desired in ComfyUI **topbar tabs**.
2. Select the first workflow in the topbar, open **Workflow Director Lab**,
   then click **+ Add current workflow**. Repeat for each workflow in order.
   The same workflow may appear multiple times; each occurrence has a distinct
   `W1`, `W2`, ... step id, which prevents native job UUID collisions.
3. Use **↑ / ↓** to change order, **Remove** to delete a row, and **Open**
   to activate the selected source workflow tab.
4. Click **Run all (N)**. The Director compiles each linked tab freshly before
   submission, checks workflow UUIDs and open tabs, freezes the entire sequence,
   then submits the run once. The backend runs steps sequentially. The Context
   registry holds committed values until the run terminates; no values survive
   into a separate later run.
5. For testing an isolated stage (for example B with GET's new optional
   missing-key fallback), click that row's **Run only**. The producer stages
   from earlier runs are *not* reused.
6. The list displays per-stage status. Once a stage is completed,
   **View result** restores its native history outputs in the corresponding
   verified workflow tab, even if it finished too fast for live websocket
   events to populate that tab.
7. The previous `Capture A`, `Capture B`, `Capture Cleanup`,
   `Run A → B` and `Run A → Cleanup → B` controls remain under the folded
   **Legacy A / B / Cleanup lab controls** panel. Its expansion state survives
   UI refreshes.

## Deliberate V1 boundaries

- **Temporary browser-memory list only**: not saved to disk, Drive or Comfy
  workflow documents, and not guaranteed to persist across browser reloads.
- No Master DAG/canvas, loops, checkpoints or automatic retry.
- **No automatic cleanup workflow insertion or internal cleaner yet.** This
  sequence editor does not depend on (or change) the previous cleanup
  experiments. The existing A→C→B legacy Lab path remains available.
- Adding only captures the **currently selected, loaded topbar tab**,
  deliberately avoiding races from switching an unverified inactive tab.
- While a run is active, reordering/removing/adding is locked. Ambiguous native
  submission/monitoring remains fail-closed until the user reconciles it.
- Repeated workflow occurrences recompile from the same current graph. Edits
  made during an active run do not alter the already frozen prompts.
- `beforeQueued` callback-dependent nodes remain a known experimental
  difference from the native frontend Run button.
- Real ComfyUI frontend acceptance is still required. Passing Node.js tests
  is not the same as validating the actual browser UI.

## Automated regression tests

`tests/lab_ui.test.cjs`: N=4 ordering and fresh snapshots; stable step IDs
through moves/deletions; reuse of a workflow with distinct step IDs; missing
or changed tabs reject pre-submit; Context PUT key discovery; in-flight locks;
per-stage `Run only`; intermediate-stage history restoration; legacy A/B/C
compatibility and missing-context toast behavior.

`DirectorEngine` and `RunPlan` already loop over `plan.steps` without a
two- or three-step restriction. The change is the user-facing sequence builder.
