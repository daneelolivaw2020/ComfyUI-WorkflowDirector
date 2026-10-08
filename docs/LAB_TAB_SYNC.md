# Lab UI — linked workflow tabs (experimental)

This feature targets the audited **ComfyUI 0.39.0 / frontend 1.53.10**
and does not change any backend execution or memory policy.

## Current behavior

1. In Comfy Settings, select **Workflow Tabs Position: Topbar**.
2. Open **two separate workflow tabs**; each should have a distinct workflow id.
3. With A active, click **Capture current as A**; with B active, click
   **Capture current as B**. These buttons now register the **tab path**
   and workflow id, as well as the initial immutable snapshot.
4. Leave **Refresh linked tabs before Run** enabled (default).
5. Change a seed, model, or LoRA in either tab. On **Run A → B**, the lab
   safely visits each linked tab, compiles it with `app.graphToPrompt()`,
   verifies its original workflow identity and freezes new prompts for this
   run. It restores the tab that the user had selected.
6. If a tab was closed, renamed/replaced, or cannot be verified, the lab
   refuses to submit the run. Reopen and capture that slot again.
7. **Show executing workflow tab** (default on) switches the ComfyUI
   canvas to the corresponding registered tab when the Director observes a
   native `in_progress` event. This does not change the submitted prompt.
8. **Notify on each workflow** (default on) shows toast notifications with
   the captured tab name on `in_progress` and `boundary_completed`.
9. **Refresh last run** refreshes only the last run's server status/memory
   observations. It does **not** recapture, recompile or restart anything.

Disable the automatic refresh checkbox to explicitly run the old frozen
captures. Leave it on for normal testing.

## Safety and scope

- Linking is **browser-memory only**, not persisted across full page reloads.
- The current lab supports two steps (A/B); the backend RunPlan remains
  N-stage.
- This extension uses the **topbar tab DOM** because Comfy does not provide
  a stable public extension API for selecting a non-active tab and compiling
  its unsaved edits. If Comfy changes this DOM, the lab fails closed rather
  than silently submitting stale snapshots.
- `app.graphToPrompt()` is not necessarily equivalent to Comfy's full
  normal Queue path for nodes that depend on `beforeQueued` callbacks.
  Existing caution still applies to such nodes.
- Notifications and tab-following are **browser UI actions**, not backend
  state transitions. If the browser closes, the backend run continues.
- The run is immutable once accepted by the backend; changing visible
  tabs afterward cannot mutate prepared steps.
- No `/free`, destructive unload, or changes to `--cache-none`.
- Unit tests use mocked tabs. **A real Colab UI acceptance run is still
  required** before release into the stable main branch.

## Manual acceptance checklist (T4)

- [ ] Open A and B in Topbar; link them.
- [ ] Change B's GGUF/LoRA and **do not** press Capture B again.
- [ ] Run A→B with fresh compile enabled. Inspect Comfy logs to confirm
      it loaded the new B model, not the old one.
- [ ] Confirm toast with each workflow name and correct tab on start.
- [ ] Confirm A and B outputs, terminal job IDs and low post-boundary VRAM.
- [ ] Close B and retry: **must error before submitting any job**.
- [ ] Reopen B, rebind, disable automatic refresh; confirm manual frozen
      snapshot behavior is explicit.
