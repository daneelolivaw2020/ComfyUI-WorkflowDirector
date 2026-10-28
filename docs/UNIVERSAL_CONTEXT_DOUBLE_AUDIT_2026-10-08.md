# Independent double audit — Universal Context / PR #6 (2026-10-08)

Branch: `feature/universal-context-nodes`. Baseline:
`feature/colab-acceptance` at `62d43b1ddb16`.
Status: **experimental; no real v0.39.0/T4 acceptance of the universal nodes yet**.

These are two independent audits with different assumptions and acceptance
criteria. Review 1 starts with **desired product outcomes, constraints and
threats**. Review 2 deliberately ignores the design claims at first and
follows **code paths, native V3 contracts, hostile inputs and false positives**.
A green CI run is evidence of the tested code only, not runtime acceptance.

## Pass 1 — Requirements-first / architecture challenge

**Target use case.** Any independent workflow may PUT a value under a
user-chosen key; subsequent independent workflows in the **same Director run**
may GET that key. The external user experience should have one general PUT and
GET, not an ever-growing family of typed nodes. Workflows are normal editable
Comfy graphs, and the backend owns sequencing rather than using a giant prompt.

**Hard constraints.**
- Google Colab Free, standard RAM, NVIDIA T4 is the acceptance target.
- Native job completion precedes Context commit; a failed/unknown job publishes
  nothing. Only one managed job runs at once.
- No model-management references or unnoticed live CUDA tensors may outlive
  the producer job through Context. Avoid `/free` and destructive unload.
- KEEP the six previous typed nodes, visual lab, known-good runtime flags and
  existing acceptance probes. Universal nodes are additions, not replacements.
- No dependency on KJNodes or other GPL implementation; adopt native Comfy V3
  generic sockets and the **interaction pattern**, not their virtual-link code.

**Architecture verdict:** The two-node public abstraction is the right UX.
But *any socket type* is not the same guarantee as *any object is transferable*.
This requires explicitly separating:
1. Socket flexibility: PUT MatchType, GET AnyType.
2. Value transport: CPU-owned copy of supported plain structures and tensors.
3. Semantic type identity: original Comfy socket type/schema, producer
   provenance and consumer expectations.
4. Resource residency: RAM now, scratch/durable/checkpoint later.
5. Lifecycle: staged vs committed, job/run boundaries, crash recovery.

**P1 findings.**

| ID | Priority | Finding | Decision |
|---|---|---|---|
| A1 | HIGH | AnyType GET accepts connections regardless of actual runtime type. Cross-workflow producer type is not inferred from the key. IMAGE vs MASK can have identical Python tensor shapes but different semantics. | Block general-release until typed key metadata + consumer contract/preflight or an equivalently safe validation mechanism exists; no need for separate public nodes. |
| A2 | HIGH | CPU-only Context increases host RAM pressure, including transient source+staged+committed+GET copies not fully covered by the 256 MiB logical budget. | Retain fail-closed limits now. Collect live peak RSS/PSS and devise scratch spill before promising large/video handoffs on the free T4. |
| A3 | HIGH | CONDITIONING is not merely tensors: actual Comfy V3 schema permits ControlNet, HookGroup, GLIGEN and other model-linked metadata. Those cannot be retained generically. | Safe pure tensor conditioning supported in principle; model-attached conditioning must be explicitly rejected or rebuilt by a reviewed adapter. |
| A4 | MEDIUM | Extension-specific opaque Python objects cannot be safely deep-copied/pickled just because their sockets are ANY. | Introduce a versioned adapter registry after the native plain-value path is accepted. Do not claim arbitrary object support prematurely. |
| A5 | MEDIUM | GET works only during active Director run. After restart/standalone B/manual Queue there is no committed Context. | Preserve safe failure; separately design checkpoint/fallback provenance. |
| A6 | MEDIUM | N-step Context keys, replacements and multiple consumers are supported by backend structure but Lab UI only exposes A/B. | Keep backend N-step; visual Master and linked reusable workflow references remain future phases. |
| A7 | MEDIUM | Runtime crashes, cancellation and external-queue interference remain wider Director release blockers. | Track separately from universal-socket PR; do not obscure them with universal Context success. |

**Priority order:** First prove V3 node loading/graphs on the known T4.
Then semantic type metadata/consumer validation, memory peak observation, and
only then general extension adapters, spill and durable checkpoints.

## Pass 2 — Code-first / adversarial review

Reviewed source paths:
- `nodes/universal_context_nodes.py`,
  `nodes/conditioning_lab.py`, `nodes/context_nodes.py`;
- `workflowdirector/universal_codec.py`,
  `workflowdirector/context_codec.py`, `workflowdirector/context.py`;
- `workflowdirector/core/{director,service}.py`,
  `workflowdirector/run_api.py`;
- `scripts/acceptance_probe.py`, `tests/test_universal_context.py`,
  visual JSON samples and their tests.

Cross-checked **tagged upstream v0.39.0**, not the moving master:
- `comfy_api/latest/_io.py`: `MatchType.Template`, generic Input/Output,
  `AnyType`, `Conditioning`, `NodeOutput`, `Schema.is_experimental`.
- `comfy_execution/validation.py`: `validate_node_input` returns True for
  ANY / COMFY_MATCHTYPE_V3, leaving cross-prompt value validation unaddressed.
- `execution.py`: native failure history includes an `execution_error`
  message with `node_type` and `exception_message`.

Links:
- https://raw.githubusercontent.com/Comfy-Org/ComfyUI/v0.39.0/comfy_api/latest/_io.py
- https://raw.githubusercontent.com/Comfy-Org/ComfyUI/v0.39.0/comfy_execution/validation.py
- https://raw.githubusercontent.com/Comfy-Org/ComfyUI/v0.39.0/execution.py

**P2 findings.**

| ID | Priority | Finding | Action/evidence |
|---|---|---|---|
| B1 | HIGH, FIXED | Negative acceptance previously passed on *any* A failure with JOB_FAILED, so a schema/import/setup failure could masquerade as correct unsafe-value rejection. | Negative probes now require native `/history/<job>` to report `execution_error` from the expected node containing the exact failure fragment; missing history fails closed. Regression tests added. |
| B2 | MEDIUM/HIGH, FIXED | `isinstance(tensor, torch.Tensor)` admitted tensor subclasses with arbitrary overridden transfer/clone methods and potentially external state. | Universal codec only accepts plain `type(tensor) is torch.Tensor`, rejecting subclasses pending safe adapters. Regression tests assert no custom transfer is called. |
| B3 | HIGH, OPEN | Universal VALUE entries record kind=VALUE rather than semantic producer socket type; GET AnyType has no cross-workflow compatibility check. | Release blocker A1; explicitly test wrong-type consumer once metadata contract is implemented. |
| B4 | MEDIUM, OPEN | Unit tests simulate Torch and native acceptance probes exercise a running Comfy process only when users run them. CI does not import actual Comfy V3 nodes/execute GPU copies. | New source/schema/API checks are supporting evidence only. Must run preflight, universal_image, universal_conditioning and negative gate on Colab T4. |
| B5 | MEDIUM, OPEN | Successful IMAGE probe checks native history/prefix, not strict pixel equality; LATENT integrity is not elementwise checked for general native output. | Add payload integrity comparisons for final runtime release proof, not just existence/metadata. CONDITIONING lab sink already checks exact tensors and metadata. |
| B6 | MEDIUM, OPEN | PUT and GET perform CPU copies; full transient RSS/VRAM peaks not observed or bounded by the 128/256 MiB logical limit. | Keep test sizes small and instrument peaks; do not claim safe large transfers. |
| B7 | MEDIUM, OPEN | No default behavior for unsupported opaque custom classes other than rejection; no adapter lifecycle/version/ownership contract. | Correct fail-closed prototype; adapter SPI needs threat review first. |
| B8 | MEDIUM, OPEN | Static writer validation only sees literal keys; linked dynamic keys can collide at native execution. | Runtime ContextRegistry already rejects duplicate stage writes and discards entire failed job. Add an integration test for dynamic collision in a later pass. |
| B9 | LOW, FIXED | New nodes were marked experimental in docs but not in V3 schema. | `is_experimental=True` now set for both; legacy typed nodes untouched. |
| B10 | MEDIUM, OPEN | Actual frontend import/serialization of visual JSON files is not tested by JSON-shape-only unit tests. | Require manual topbar import, link display and A→B run before release. |

**Positive invariants inspected and retained:** Native Comfy job terminal state
gates `commit_step`; Context cloning is CPU-only and detached for known tensor
types; preflight size check occurs before GPU→CPU copies; duplicate literal and
runtime writers fail; previous keys survive successful replacements only when
RAM co-existence budget permits; failed/abandoned steps cannot publish, and
the run-scoped session is torn down after the service exits.

## Acceptance status — never conflate evidence

| Evidence | Status |
|---|---|
| Earlier six typed nodes STRING/IMAGE/LATENT/failure real Colab | PASSED (previously observed by user) |
| Earlier A/B topbar refresh and closed-tab rejection real Colab | PASSED (previously observed by user) |
| Universal CPU codec / staged visibility / regression tests | GitHub CI (Python 3.11/3.13) |
| Universal MatchType/AnyType existence in Comfy v0.39.0 source | SOURCE CONFIRMED |
| Universal V3 actual registration / frontend MatchType visual behavior | NOT YET RUN ON T4 |
| Universal IMAGE / CONDITIONING / unsafe-object native jobs | NOT YET RUN ON T4 |
| End-to-end heavy Klein Q4→Q6 with universal Context | NOT YET RUN ON T4 |
| Per-job memory peaks / scratch spill / Checkpoints | NOT IMPLEMENTED |

## Current release recommendation

Keep PR #6 **draft**, based on `feature/colab-acceptance`. Do not merge
into main or replace known-good notebooks/workflows on unit-test evidence.
When at Colab, install this branch using the existing selectable cell,
restart **only Comfy's process**, disable Auto Queue and run these cases in
order:

1. `preflight`
2. `string`, `image`, `latent`, `failure` (legacy regressions)
3. `universal_image`
4. `universal_conditioning`
5. `universal_unsafe_conditioning` (must fail A for the **expected reason**)
6. Import both visual CONDITIONING JSON files and run A→B from the Lab panel.
7. Only then: real text-encoder conditioning and heavy Klein Q4/Q6.

Do not use destructive unload, untrusted pickle, new Torch installs, or paid
Colab resources to make these tests pass.
