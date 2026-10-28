# Second architecture and code audit — 2026-10-08

## Scope and objective

Review the original WorkflowDirector objective against the latest laboratory results,
the backend orchestration code on `main`, and the tab-linked UI changes proposed
in draft PR #1. Target: ComfyUI 0.39.0, frontend 1.53.10, Colab Free T4,
standard RAM, ordinary GGUF model paths.

**Core product contract**: schedule independent top-level workflow jobs in an
ordered N-step RunPlan; never retain MODEL/CLIP/VAE objects in durable cross-step
Context; allow typed IMAGE/LATENT/STRING Context eventually; preserve ordinary
Comfy workflow editing; freeze executable prompts per run; never rely on unload
nodes or a kernel restart.

## Laboratory facts — observed, not extrapolated

- Native smoke A→B succeeded, with distinct jobs and boundary observations.
- With normal Comfy executor cache, heavy A completed with final RSS ≈8.7458
  GiB, Torch allocated ≈4.5785 GiB, device used ≈5.0907 GiB and 3 loaded
  model entries. A terminal job does not imply model release.
- With `--cache-none`, the identical A completed with final RSS ≈2.8099
  GiB, Torch allocated ≈0.0079 GiB, device used ≈0.1844 GiB and zero loaded
  models. This is an observation for the tested model stack, not a generic
  guarantee of zero leaks.
- After a clean Comfy restart, a real A→B run exercised Klein Q4 + a
  mostly-Q4 Qwen in A and Klein Q6 + Qwen Q6 in B, as independently evidenced
  by qtype logs; A and B both completed. Final RSS ≈2.7255 GiB and device
  used ≈0.1844 GiB.
- Repeating this pair three more times on the same process yielded final
  RSS ≈2.6473, 2.5997 and 2.5726 GiB, with device used ≈0.1844 GiB
  and 0 model entries each time.
- Anonymous PSS in those repeated observations rose from ≈2.2308 GiB to
  ≈2.3247 GiB while file-backed PSS fell. Three repeats neither prove a
  leak nor prove indefinite stability.
- A previous test of model changes was invalidated by a stale B capture.
  Recapture correctness is therefore a *release-blocking UX issue*.

## Architecture check

| Requirement | Implementation / result | Gate |
| --- | --- | --- |
| Independent prompt jobs | DirectorEngine + native Jobs API | Verified in T4 |
| Strict serial submission | One job/step, await terminal, then observer | Verified in T4 |
| Immutable per-run prompt | PreparedStep canonical JSON freeze | Unit-tested |
| Conservative lost ACK recovery | Deterministic job IDs / visibility lookup | Unit-tested |
| Queue interference detection | Jobs API polling; not a global Comfy queue mutex | Partial |
| Memory boundary | Read-only observations, no /free | Measured in T4 |
| Cache policy | `--cache-none` supplied by Comfy launch, not enforced by Director | Environmental dependency |
| Host RAM behavior | RSS/PSS post-step, not per-job peak | Partial |
| Visual follow / tab binding | PR #1, tested with mocks | Real-UI test pending |
| Frontend normal-Queue equivalence | Uses graphToPrompt, not guaranteed for beforeQueued nodes | Open compatibility gap |
| N-stage support | Backend RunPlan accepts N; UI only A/B | Partial |
| Context typed values | Design only, IMAGE/LATENT/STRING not yet implemented | Open |
| Atomic Context patch commit | Design only | Open |
| Durable backend recovery | In-memory RunRecord; no crash-safe journal/checkpoint | Open |
| Master visual graph | Design only | Open |

## Second-pass frontend findings and fixes in PR #1

1. **Stale snapshots**: old Capture A/B was not updated after canvas changes.
   New default re-compiles linked tabs immediately before submission and freezes
   prompts afterward; closed/missing tab aborts without POST.
2. **Tab identity collision**: two different tabs can accidentally carry the
   same workflow UUID. New guard rejects duplicate UUIDs to avoid mistaking the
   wrong canvas for the intended workflow.
3. **Asynchronous tab restoration**: a selected visual tab does not guarantee
   its graph has finished loading. New code verifies the original canvas ID
   after returning to its tab, before posting the plan.
4. **Transient UI polling disconnection**: losing status while the backend is
   still running previously released frontend busy state. New bounded retry and
   uncertain-state guard prevents submitting another job while the last
   backend run remains unknown.
5. **Ambiguous POST acceptance**: now preassigns a client-side run UUID and
   retains it before POST. A lost/malformed acknowledgement locks new Run
   attempts and permits querying the exact run by UUID. No blind retry.
6. **Stage visibility**: in-progress native event switches to linked tab
   (optional); `boundary_completed` displays a completion notification.
   Follow/navigation is UI-only and does not mutate the prepared prompt.
7. **Frontend DOM coupling**: implementation currently inspects topbar
   `data-workflow-path` and selected-Tab markup; unsupported tab layouts
   fail closed. This must be verified in real frontend 1.53.10.
8. **Browser-only bindings**: refresh/reload loses linked tab paths and run
   list. Native backend run continues, but current panel does not restore
   browser state automatically.

## Release blockers for the draft UI

- Manual smoke in real Comfy 0.39/1.53.10 with *two topbar tabs*.
- Modify B after linking, run A→B without manual recapture; inspect qtype
  log proving the latest B values were actually used.
- Verify active tab accurately follows each job, not a stale tab.
- Verify toasts and correct name on run start and boundary completion.
- Close B and confirm no backend submission; verify duplicated UUID refusal.
- Disconnect/reconnect status during an active run; verify ambiguous
  state blocks second submission.
- Re-check fixed-seed workflows with rgthree Power LoRA specifically, because
  `graphToPrompt()` alone does not guarantee beforeQueued equivalence.
- Confirm CI succeeds on the final PR head for JS tests and Python 3.11/3.13.

## After UI acceptance: recommended priority

1. Implement a minimal typed Context API (Put/Get for STRING, IMAGE, LATENT).
2. Ensure CPU-only tensor storage and strict model object rejection.
3. Stage mutations during execution; commit atomically only on terminal success.
4. Prove A produces an IMAGE/LATENT consumed by B with different GGUF
   configurations and `--cache-none`, without retaining GPU references.
5. Expand from A/B lab to genuine N-stage Master model.
6. Add peak per-step RAM/VRAM observations, anon/file PSS and cgroup
   headroom; test longer varied model chains.
7. Add durable run metadata/checkpoint recovery in Google Drive or
   configured durable storage.

Do **not** add destructive `/free`, `unload_all_models`, or
HardDelete as a reaction to raw RSS. Distinguish process working set, mmap,
allocator caches, in-progress peak, and true retained model references.

## Operational hygiene

The user's locally edited Colab notebook had a Civitai token literal. Move
secrets to Colab Secrets and rotate/revoke the exposed token; never copy
credentials into committed notebooks or diagnostic packages.

This review is a code + source + mock/CI audit, **not** a claim that the new
frontend code has already been accepted in real Colab.
