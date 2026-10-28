# Read-only process RAM attribution — PSS

This change extends existing per-boundary measurements (BASELINE,
POST_IMMEDIATE and POST_WINDOW_*), without unloading any model or changing
execution order.

## New snapshot fields

On Linux (including Colab T4), WorkflowDirector reads:
\`/proc/<pid>/smaps_rollup\` and records:

- \`process_memory.pss_anon_gib\`: proportional anonymous pages;
- \`process_memory.pss_file_gib\`: proportional file-backed pages;
- \`process_memory.pss_shmem_gib\`: proportional shared-memory pages;
- \`process_memory.private_dirty_gib\`, plus PSS, RSS, swap and clean-page fields.

The run summary compares anonymous and file-backed PSS separately with the
same run baseline. The Lab table now includes those absolute/delta values.

If \`smaps_rollup\` is unavailable or permission is denied, the parser returns
an empty measurement and displays \`—\`. It never fabricates zeros.

## What the numbers mean

RSS going down does **not** prove anonymous memory was reclaimed, and
anonymous PSS increasing does **not** independently prove a leak.
File-backed PSS may decline as mmap pages are released; anonymous PSS may
remain resident inside native allocators, PyTorch/CPU buffers or libraries.

PSS is proportional: it attributes shared physical pages across mappings,
but does not identify the owner Python object. GPU utilization remains a
**separate** measurement.

As before, POST_WINDOW_END is the end of a *timed observation*, not proof
that Comfy ran GC or that memory reached a settled equilibrium.

## Performance and scope

\`smaps_rollup\` is read **only at existing observation points**, currently
around four times per workflow boundary plus baseline. This development
change does not continuously sample memory *during* a model run and does
not claim to capture RAM or VRAM peaks.

No changes to cache policy, \`--cache-none\`, Comfy/model unloading or
Context semantics. Tests exercise the pure parser, empty fallback and
baseline-relative memory analysis without a GPU.

Real Colab acceptance for this UI visualization remains pending.
