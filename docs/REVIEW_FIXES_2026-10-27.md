# Context and monitoring review fixes — 2026-10-27

Baseline: `487af580115206f83b7e56f389f5f64eb183fec1`.

## Result

1. Active-job transport failures now pause and retry queue inspection without
   ending the Context transaction or submitting a successor. Recovery has a
   five-second budget starting after the first failed request, bounded further
   by the current job's remaining timeout. Recovery HTTP lookups are themselves
   limited to that remaining budget. The original lookup retains the adapter's
   normal request timeout. Protocol failures and observed foreign jobs remain
   fatal. Exhaustion stops sequencing with QUEUE_STATE_UNCERTAIN and explicitly
   warns that the native job may still be running; no native cancellation is
   implied. Existing service teardown retires the abandoned Context transaction.
2. Typed IMAGE/LATENT paths reject Tensor subclasses before invoking their
   methods, matching the universal codec's restriction. Returned copies must
   be independent, valid base tensors with the expected payload size, detached
   and CPU resident.
3. Terminal run status clears the live Context snapshot while preserving the
   last run's metadata. An inspection token invalidates delayed responses when
   a run ends or a new run starts, and prevents older inspection responses from
   overwriting newer ones.

Normal node IDs, sockets, prompt/job contracts, sequence ordering and optional
cleanup selection are unchanged. No new dependency or ComfyUI version upgrade
is required by these fixes.

## Verification

- Backend suite: **130 passing tests** (119 baseline + 11 regressions).
- Frontend suite: **37 passing tests** (35 baseline + 2 regressions).
- Python compilation, JavaScript syntax and `git diff --check` passed.
- Codec and frontend regressions were run against the original implementation
  first and failed, then passed after the fixes.
- Lifecycle regression: a native producer writes while queue inspection is
  recovering; the transaction stays active, the write commits, and B reads A's
  data without any duplicate submissions.
- Failure regression: persistent queue uncertainty remains bounded, hanging
  recovery lookups are cancelled, foreign jobs are rejected after reconnect,
  and the next workflow is not submitted on failed recovery.

Two review passes checked integration/correctness and adversarial lifecycle:
the fixes use only existing adapter and Tensor contracts; recovery cannot
resubmit prompts; asyncio cancellation still propagates; terminal Context
metadata remains historical rather than live. The basic native prompt/jobs
contracts were checked against the official ComfyUI v0.43.0 source during the
preceding review. This is not a new full compatibility certification: the last
recorded runtime audit remains the version in COMPATIBILITY.md.

## Colab acceptance still required

The tests above use simulated native jobs/tensors/frontend tabs. They do not
claim new GPU execution or measured RAM/VRAM release. Before publishing these
changes over the working GitHub version, validate a Colab/T4 session with:

- A -> B, verifying the generated input reaches B through Context;
- B alone with a missing Context key and its existing switch fallback;
- an N-workflow sequence, with and without the existing optional cleanup;
- terminal success/failure, confirming Context keys are labelled released;
- normal typed IMAGE/LATENT transfer as well as the existing universal nodes.

The fixes are kept in a local commit until that runtime acceptance is recorded.
