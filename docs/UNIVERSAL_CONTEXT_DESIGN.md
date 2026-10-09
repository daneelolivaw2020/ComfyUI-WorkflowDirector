# Universal Context nodes — experimental branch

This document specifies an opt-in feature. It does **not** replace the
six typed Context nodes already accepted on the Colab Free NVIDIA T4.

## Why not copy KJNodes Set/Get?

KJNodes Set/Get offers excellent UI conventions (key naming, inferred socket
types, jump links, subgraph support). Its virtual links are resolved as part of
one compiled prompt. They are **not** storage across separate native Jobs.

We therefore reuse **native ComfyUI v0.39.0 V3 socket features**, not
KJNodes' GPL-3.0 implementation. No KJNodes source is incorporated and no
dependency is added.

- PUT: V3 MatchType input/output sharing one template (type-preserving pass-through).
- GET: V3 AnyType output (can connect to arbitrary consumer sockets).
- The two workflows do not share a type-inference graph. ANY does not enforce
  cross-workflow socket compatibility: incompatible consumers may fail at runtime.

References:
- https://github.com/Comfy-Org/ComfyUI/blob/v0.39.0/comfy_api/latest/_io.py
- https://github.com/kijai/ComfyUI-KJNodes (Set/Get design reference)

## New nodes

| Node ID | Visible title | Input | Output | Purpose |
| --- | --- | --- | --- | --- |
| WorkflowDirectorContextPutUniversal | PUT INTO CONTEXT (Universal) | key: STRING; value: MatchType | MatchType passthrough | Stages detached copy of input |
| WorkflowDirectorContextGetUniversal | GET FROM CONTEXT (Universal) | key: STRING | AnyType | Retrieves a clone of committed value |

All existing typed nodes and saved workflows retain their original IDs
and schemas, unchanged. The universal Get can consume keys committed by
the six typed nodes, but typed Get does not treat a generic VALUE entry as
STRING/IMAGE/LATENT.

## Storage and safety contract (initial slice)

The new codec accepts **data by structure**, not a whitelist of ComfyUI socket
names. VALUE entries currently support:
- None, bool, int, float, str, bytes, bytearray;
- ordinary lists, tuples and dictionaries with STRING keys, nested to 32 levels;
- dense Torch tensors (CPU or CUDA input), detached/copied into CPU RAM;
- ordinary CONDITIONING structures comprising these values;
- composite custom-node outputs **only if** they use the same safe plain-data
  structure.

It rejects:
- live MODEL, CLIP, VAE, ControlNet/GLIGEN objects, patchers, arbitrary Python
  class instances or containers embedding them;
- sparse/quantized/meta tensors; cycles; excessive nesting or components;
- anything exceeding existing Context size limits.

This conservatism preserves the system's original goal: no silent model/VRAM
retention across independent workflow memory boundaries. A conditioning with a
ControlNet object will fail explicitly; it cannot be blindly cloned.

Limits inherited from Context: **128 MiB per entry** and **256 MiB combined
committed+staged**. A tensor is individually capped at 128 MiB. They represent
logical payload bytes, **not** process-RSS or transient copy peaks. Recursive
values have an additional limit of 10,000 members and 32 levels.

Writes are transactional: staged during step A; committed only if native Job A
reaches `completed`; rolled back otherwise. GET returns independent clones.
The Context session ends with the Director run. No `/free`, forced unload,
pickle, scratch spill or checkpoint is introduced.

### Deliberately unresolved

- Fully arbitrary extension-specific opaque objects require adapters capable
  of producing safe CPU data/reconstruction (not attempted here).
- GET's AnyType socket cannot infer its concrete type solely from a key in
  another workflow; actual consumer compatibility still needs runtime checks.
- Model-coupled conditioning cannot survive a boundary without explicit
  reconstruction. That is distinct from pure tensor conditioning.
- Manual Queue PUT is passthrough only and GET requires active Director run,
  same as existing nodes.
- Neither backend process restarts nor saved/independent Master runs preserve
  Context yet.

## Acceptance gates

1. CI: typed regression suite still passes; new tests for nested CONDITIONING,
   deep cloning, early rejection before CPU transfer, no model references,
   cycles, byte budgets and static duplicate writers.
2. Colab v0.39.0, T4, `--cache-none`: verify eight Context nodes registered
   (six legacy + two universal) and existing four acceptance cases stay green.
3. Two topbar workflows: A with a native producer → universal PUT key
   `test.value`; B with universal GET `test.value` → suitable consumer;
   confirm native B output, two completed jobs and manifest type VALUE.
   Start with STRING via a STRING-producing upstream node, then IMAGE/MASK.
4. CONDITIONING producer (without ControlNet/hook objects) → universal PUT;
   consumer in B → compatible sampler: actual execution and output required.
5. Negative: model-coupled conditioner rejected and B never submitted;
   failing A must not commit; close B tab and confirm zero jobs.
6. Heavy A Klein Q4 → B Klein Q6, with memory measurements and correct
   outputs; inspect RSS/PSS/VRAM after each job. No claims of GPU peak
   telemetry or generic unload behavior.

Do not merge to main or replace existing saved workflows until real frontend
and T4 acceptance gates pass.
