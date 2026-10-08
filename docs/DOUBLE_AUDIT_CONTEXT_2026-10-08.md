# Double audit — WorkflowDirector architecture + code

Scope: stacked development branch `feature/double-audit-hardening` built on
PR #1 (Lab UI), PR #2 (Context), PR #3 (PSS). No merges to `main`.

Audit technique:
1. **Requirements-first** comparison to Architecture / Validation Plan and the
   Colab T4 Q4↔Q6 experiment data.
2. **Independent code-first** review of native ComfyUI 0.39.0 executor context,
   V3 node schema examples, transaction flow, RAM budget, timeout failure
   paths, frontend tab coupling, CI mocks and Linux PSS parser.

## Observed / proven

- Native sequential A→B jobs, terminal status, and post-job memory sampling
  were exercised in real Colab Free T4 before these PRs.
- `--cache-none` worked for the tested GGUF/LoRA combinations and terminal
  resident VRAM, but no arbitrary model or long-chain stability guarantee.
- ComfyUI 0.39.0 sources confirm the native prompt UUID is accessible during
  V3 node execute via `comfy_execution.utils.get_executing_context()`
  and that native Jobs terminal state follows prompt execution.
- Core RunPlan is N-stage, but Lab UI has only A/B; no Master editor.
- Context Put/Get nodes, CPU tensor codec, Context lifecycle and PSS snapshots
  pass isolated CI tests; **they have not yet been loaded and exercised
  end-to-end with real ComfyUI in Colab**.

## Pass 1 — logic and architecture

| Area | Status | Remaining issue |
| --- | --- | --- |
| Native independent workflows | proven for A/B | N-stage UI unbuilt |
| Native Jobs API and sequential boundaries | proven for A/B | no global queue lock; only interference detection |
| Context isolation across run and steps | implemented and unit-tested | no durable persistence |
| Completion-triggered Context commits | implemented and unit-tested | error/timeout leaves native job potentially active |
| Image/latent CPU storage | strict codec implemented | live CUDA/Comfy V3 acceptance pending |
| Context without hidden model references | MODEL/CLIP/VAE blocked | Get clones and live graph outputs also consume memory |
| Memory metrics | RSS + PSS + Torch + device | post-job only; no in-job peaks |
| `--cache-none` | proven favorable in T4 | external Comfy startup setting |
| Workflow tab sync | unit-tested | frontend DOM dependency; real tab/navigation acceptance pending |
| User-independent execution | backend owns run | backend runtime restart recovery pending |

## Pass 2 — bugs and safety corrections in this PR

**Finding A (high): replacement memory was undercounted.** An update to a
Context key might temporarily hold old and new CPU values simultaneously
but previous accounting checked only the post-commit logical footprint.
Fixed: account for all currently committed **plus staged** payload bytes
until the atomic commit, even on replacements. Under pressure, raise an
explicit budget error rather than silently exceed the configured bound.

**Finding B (high): GPU→CPU copying occurred before the Context budget
check.** A value too large for available Context could consume host RAM
during `copy_in` only to be rejected afterward.
Fixed: codec now implements `estimate_size` for STRING/IMAGE/LATENT,
validates all latent metadata/tensor sizes without first cloning, and
checks per-entry and aggregate Context budgets before copying. The
reported estimate must equal the actual copied payload size.
Regression tests verify rejection happens **before** any copy.

**Finding C (medium): late native jobs could look like manual Comfy
prompts after Context teardown.** If Director aborted a job while native
Comfy was still running, a late Put could have found an idle Context and
silently acted as a normal manual pass-through.
Fixed: Context now keeps a bounded set of 1024 tombstones for abandoned
job IDs; delayed Put for one of those jobs raises an explicit error.
Tests exercise orphaned IDs and bound memory of tombstones.

## Important unresolved risks (explicit release blockers)

1. **Comfy UI actual integration** — V3 nodes and tab DOM must be tested in
   audited ComfyUI 0.39.0/frontend 1.53.10, including `beforeQueued`
   behavior, stale snapshots, wrong workflow UUID, and tab switching.
2. **Transient memory peaks** — the current resident+staged estimate does
   not cover source graph tensors, the temporary copy made by Context Get,
   Python/Torch tensor metadata, CUDA buffers or pinned allocations.
   A 256 MiB Context logical budget is **not** a 256 MiB cap on total host
   RAM or job peak. Need peak telemetry and possibly disk scratch.
3. **Native cancellation/timeout** — cancelling/aborting Director does
   not automatically cancel its native Comfy job. Code fails closed, and
   new Director runs check the native active queue, but a proper
   reconciliation/cancel-and-wait protocol is not yet implemented.
4. **Backend crash recovery** — RunRecord and current Context are in
   process memory only. Browser disconnect is different from backend
   death; no persistent manifest/checkpoint yet.
5. **Standalone Get** — standalone Context Put is pass-through when
   no Director is active. Get requires committed run Context and cannot
   independently reproduce downstream B without a fallback or checkpoint.
6. **Multi-version workflow support** — current frontend integration
   targets topbar markup of one audited frontend release, not a public
   versioned tab API.
7. **Global queue exclusivity** — interference checks happen on
   observations/polls rather than via an atomic lock across all native
   Comfy producers; another client can race with the Director.
8. **Resource provenance** — PSS anonymous/file distinguishes page
   classification, not ownership or proof of a memory leak. Context RAM
   is intentionally held across A→B and should not be counted as an
   unexplained leftover model allocation.

## Acceptance order after development

- CI green for current PR head (Python 3.11/3.13, JavaScript).
- Real Comfy UI 0.39.0: test tab A/B recapture and start toasts.
- Small STRING A→B via Context nodes.
- Small IMAGE and LATENT A→B, verify CPU residency/pixel or tensor
  integrity, and failure-discard semantics.
- Heavy Q4→Q6 A→B with Context; post-job RSS/PSS and actual per-job peaks.
- Only then prepare a staged merge to `main`. Keep startup flags fixed.

No aggressive `/free`, `unload_all_models()`, HardDelete or kernel
restart was introduced in this audit.
