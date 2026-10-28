# WorkflowDirector: Context explorer, key picker and optional cleanup boundary

Status: **experimental; implemented on `feature/universal-context-nodes`, not accepted in a real Colab T4 until user retests.** Do not merge PR #6 as accepted yet. Stable `feature/colab-acceptance` unchanged.

## Product behavior

1. **Context is run-scoped**, transactional, and owns detached CPU copies. PUT stages a copy while its native job executes; it is published only after native status COMPLETED. B GET reads the committed copy. The service's `end_run` destroys all committed/staged data on every terminal run exit.
2. **Context Explorer** in WorkflowDirector Lab shows three distinct states: planned keys found in captured producer PUT nodes, live committed keys from `GET /workflowdirector/context`, and the last-run **metadata snapshot only** retained in the RunRecord. The API does not reveal payload values, tensor contents, or uncommitted writes.
3. The ComfyUI universal GET node retains its manually editable `key` STRING input and adds a helper **`context_key_picker` combo**, drawing candidates from captured PUT keys, active committed keys and last-run key names. Choosing a key updates the original `key` widget; the combo is not a second API input. Dynamic/link-computed keys must still be entered or connected manually.
4. The run record includes bounded **shape metadata** (`context_inspection`): kinds, container structure, tensor dimensions and dtypes. This is introspection **of copies already held in Context**, not a new retention of live tensors. Container keys may be shown; string, numeric and tensor values are not.
5. For fast B, the Lab reads canonical completed output metadata from native `GET /history/{job_id}` and reapplies it **to the matching, verified B tab only** when the "Show executing workflow tab" option is enabled. This fixes a probable missed-websocket-event race. Colab frontend acceptance remains required; no claim that it fixes all display nodes.
6. **Optional C workflow**: `Run A → Cleanup → B` (distinct from the original A→B). C is an independent native job inserted **after A commits Context and before B starts**. C cannot contain any `WorkflowDirectorContext*` nodes; it cannot read or overwrite keys. After C completes, the Director verifies that committed Context key/type/size metadata remains unchanged before proceeding. A cleanup crash or failed native job stops the run; B is not queued.
7. Example standalone `workflows/cleanup_between_A_B_C.json` uses a **tiny EmptyImage trigger → MemoryStatus → MemoryManager → RAMCleanup → SaveImage**, copied from the user-proven **node class names and settings**; it is not itself accepted on T4 yet. The cleanup nodes are third-party dependencies and are used **only if the user selects this option**.

## Context preservation contract

- **CPU ownership**: the universal codec clones dense ordinary Torch tensors to detached CPU storage; ordinary dict/list/tuple data is cloned recursively. Comfy model cache unload and `torch.cuda.empty_cache` should not erase Context-owned CPU objects. Normal Python `gc.collect()` cannot collect objects still referenced by the live registry.
- **Sequence**: A native COMPLETED → `commit_step(A)` → optional separately scheduled C → `commit_step(C)` (empty) → guarded boundary → `begin_step(B)` → B GET.
- **Guard limitation**: the committed-manifest comparison detects missing/replaced keys and size/type changes, **not an in-place byte-level mutation** of a tensor without changing its dimensions. This is supplemental; real correctness relies on independent ownership and not giving cleanup code direct registry access.
- **Resource limits**: current universal codec accepts only plain data and ordinary dense tensors (max 128 MiB per entry, 256 MiB total). Live MODEL, CLIP, VAE, arbitrary custom objects, unsupported tensor subclasses and GPU ownership are intentionally excluded.
- **No implicit unload**: WorkflowDirector core still does **not** call Comfy `/free`, force-unload loaded models, clear global execution caches, or invoke CUDA APIs. The example C job intentionally uses the user's already-tested cleanup nodes but its different execution placement must be tested on Colab before relying on it. It may fail or be unsafe in some setups.
- A `completed` run's `context_inspection` and `context_manifest` are *historical metadata only*; B-only on a new run **cannot** read previous Context.

## Developer verification and limitations

- Unit tests cover: exact metadata-only inspection, staged values not appearing before commit, GC preserving committed data, suspicious boundary edits stopping B, A→C→B scheduling and Context preservation, C preflight rejection, frontend key selector, latest-run identity and native image output recovery.
- Node preview restoring and dynamic `combo` UI behavior still require real ComfyUI v0.39.0 / frontend 1.53.10 browser acceptance, especially with subgraphs and the Vue frontend.
- The inspector lists **known/planned keys**, not an omniscient database of all possible dynamic PUT keys before they execute.
- Do not commit model credentials, tokens, user data, images, or downloaded weights. Only shape/name metadata appears in API responses.

## Real Colab integrated acceptance (single workflow-level test)

1. Keep `WD_REF = "feature/universal-context-nodes"`; rerun the custom-node install/update cell and restart **only the ComfyUI process**. Refresh the browser. No need to reboot Colab or download a model.
2. Open `universal_image_A.json` (or your own Load Image→PUT), `cleanup_between_A_B_C.json` and `universal_image_B.json` (GET→SaveImage or PreviewImage) in **three distinct topbar tabs**, each with its own UUID.
3. Capture A, B and Cleanup C with their respective buttons. Choose **Run A → Cleanup → B**. Compare with original **Run A → B** if cleanup causes trouble. Do not enable unknown aggressive unload mechanisms.
4. Confirm A commits `demo.image`; C runs independently and does not publish Context; B consumes the preserved value; terminal phase is `completed`. The enhanced explorer should show the key, its payload shape and last-run snapshot after teardown.
5. With **Show executing workflow tab** checked, B's visible PreviewImage output should be restored by history replay even for a fast job. If that still fails, read `/history/{job_id}` from native Comfy as the source of truth and report browser/frontend behavior separately.
6. If any cleanup node crashes or refuses to run standalone, stop using the C button and return to A→B; the default path never uses C. Report the native error or crash details instead of retrying destructive cleanup blindly.

**The C JSON was assembled using the same node names and boolean settings present in prior user-provided real A/B workflows. Its standalone scheduling remains unverified in the user's active Comfy environment.**

## Real Colab report: UI output restoration and A→Cleanup→B — 2026-10-09

**User-observed integrated acceptance (not an automated benchmark; no raw native logs or memory measurements supplied):**

- A→B with an IMAGE Context payload now **shows the image in B's PreviewImage** and produces **Get Image Size output** visible in the UI. Previously the same results existed in native history but the frontend displays remained empty. This supports successful behavior of the newly implemented history-based UI restoration in this Colab session; the exact underlying event-race cause remains an inference, not a proven diagnosis.
- The optional **A→Cleanup→B** path also appeared to execute correctly. The user changed the source image and reported that B recovered it after the cleanup stage, **without losing Context**.
- Thus the key product path is accepted functionally for this IMAGE scenario: A commits → optional separate native cleanup C → B gets Context. This **does not** demonstrate that cleanup returns RAM/VRAM to a baseline, unloads every model, or works with every third-party cleanup node or large-model workflow.
- Continue to keep the experimental branch separate from the accepted baseline until real memory/cleanup stability has been assessed. Avoid changing the successful universal PUT/GET transport just to chase a visual-only issue already resolved in this scenario.

**Remaining work:** evaluate true GPU/RAM residuals and stability across repeated heavy A→C→B cycles (with the user's already-working cleanup nodes), polish Context key picker / explorer on a real frontend, and provide explicit diagnostics when native cleanup crashes or conflicts with other jobs.

## Standalone B and missing Context fallback — 2026-10-09

**User case:** Run B manually (or B only) without running A's PUT `render1` first. The current GET formerly raised `WorkflowDirectorContextNotFound`, preventing the `rgthree Any Switch` from using a separate `Load Image` input.

**Implemented behavior:**
- Universal GET now has an optional Boolean `error_if_missing` (**default false** for compatibility with existing saved workflows).
- If the Context key exists, GET returns a detached copy exactly as before.
- If the Context key is absent in an active Director run or B is queued manually outside Director, GET returns **`None`** with UI text marker, emits a Python warning, and the frontend displays a nonfatal warning toast. This supports `rgthree Any Switch`, which explicitly chooses the first input whose value is not `None`.
- If `error_if_missing=true`, GET instead raises a specific `ContextNotFound` error, useful for strict production sequences.
- Invalid keys, foreign jobs while Director runs, abandoned/retired jobs, and codec corruption **still raise**; optional missing-key mode must not bypass the existing ownership/transactional safety.
- **Correct B wiring:** GET value directly to `rgthree Any Switch` input 1; `Load Image` fallback to input 2; connect `Preview Image` / processing **after** the switch. Putting `Preview Image` between GET and switch can crash on `None` before the fallback runs.
- There is no persistent Context across runs: B-only always sees an empty Context unless the same Director run committed that key before B. The fallback is not a checkpoint mechanism.

**Validation:** backend tests and browser-controller tests run in CI; real ComfyUI/Colab acceptance of `None` through rgthree switch and UI toast is still needed. GET typed legacy nodes remain strict; only `WorkflowDirectorContextGetUniversal` gained optional semantics.
