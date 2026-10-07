import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const state = {
  A: null,
  B: null,
  lastRunId: null,
  lastRun: null,
  pollToken: 0,
  isRunning: false,
};

function notify(severity, summary, detail = "") {
  const toast = app.extensionManager?.toast;
  if (toast?.add) {
    toast.add({ severity, summary, detail, life: 4000 });
    return;
  }
  console.log("[WorkflowDirector]", summary, detail);
}

function snapshotCompiled(compiled) {
  return JSON.parse(JSON.stringify(compiled));
}

async function capture(slot) {
  const compiled = await app.graphToPrompt();
  const frozen = snapshotCompiled(compiled);
  const workflowId =
    typeof frozen.workflow?.id === "string" && frozen.workflow.id
      ? frozen.workflow.id
      : "lab-" + slot.toLowerCase() + "-" + crypto.randomUUID();

  state[slot] = {
    step_id: slot,
    workflow_id: workflowId,
    name: "Lab Workflow " + slot,
    prompt: frozen.output,
    workflow: frozen.workflow,
  };

  notify("success", "Workflow " + slot + " captured");
  refreshAllPanels();
}

function metricValue(metrics, key) {
  const value = metrics?.[key]?.current;
  return value == null ? "—" : String(value);
}

function deltaValue(metrics, key) {
  const value = metrics?.[key]?.delta;
  if (value == null) return "—";
  return value > 0 ? "+" + value : String(value);
}

function makeObservationTable(memorySummary) {
  const table = document.createElement("table");
  table.style.width = "100%";
  table.style.borderCollapse = "collapse";
  table.style.fontSize = "12px";

  const headers = [
    "Step",
    "Observation",
    "RSS GiB",
    "Δ RSS",
    "Torch alloc",
    "Δ alloc",
    "Torch reserved",
    "Δ reserved",
    "Device used",
    "Δ used",
    "Sys avail",
    "Δ avail",
    "Models",
  ];

  const head = document.createElement("tr");
  for (const label of headers) {
    const th = document.createElement("th");
    th.textContent = label;
    th.style.textAlign = "left";
    th.style.padding = "4px 6px";
    th.style.borderBottom = "1px solid var(--border-color, #555)";
    head.appendChild(th);
  }
  table.appendChild(head);

  const baselineMetrics = memorySummary?.baseline?.metrics;
  if (baselineMetrics) {
    const baselineValues = [
      "—",
      "BASELINE",
      metricValue(baselineMetrics, "process_rss_gib"),
      deltaValue(baselineMetrics, "process_rss_gib"),
      metricValue(baselineMetrics, "cuda_allocated_gib"),
      deltaValue(baselineMetrics, "cuda_allocated_gib"),
      metricValue(baselineMetrics, "cuda_reserved_gib"),
      deltaValue(baselineMetrics, "cuda_reserved_gib"),
      metricValue(baselineMetrics, "cuda_device_used_gib"),
      deltaValue(baselineMetrics, "cuda_device_used_gib"),
      metricValue(baselineMetrics, "system_available_gib"),
      deltaValue(baselineMetrics, "system_available_gib"),
      metricValue(baselineMetrics, "loaded_model_entries"),
    ];
    const baselineRow = document.createElement("tr");
    for (const value of baselineValues) {
      const td = document.createElement("td");
      td.textContent = value;
      td.style.padding = "3px 6px";
      td.style.borderBottom = "1px solid var(--border-color, #333)";
      baselineRow.appendChild(td);
    }
    table.appendChild(baselineRow);
  }

  for (const step of memorySummary?.steps ?? []) {
    for (const observation of step.observations ?? []) {
      const metrics = observation.metrics ?? {};
      const values = [
        step.step_id,
        observation.label,
        metricValue(metrics, "process_rss_gib"),
        deltaValue(metrics, "process_rss_gib"),
        metricValue(metrics, "cuda_allocated_gib"),
        deltaValue(metrics, "cuda_allocated_gib"),
        metricValue(metrics, "cuda_reserved_gib"),
        deltaValue(metrics, "cuda_reserved_gib"),
        metricValue(metrics, "cuda_device_used_gib"),
        deltaValue(metrics, "cuda_device_used_gib"),
        metricValue(metrics, "system_available_gib"),
        deltaValue(metrics, "system_available_gib"),
        metricValue(metrics, "loaded_model_entries"),
      ];

      const row = document.createElement("tr");
      for (const value of values) {
        const td = document.createElement("td");
        td.textContent = value;
        td.style.padding = "3px 6px";
        td.style.borderBottom = "1px solid var(--border-color, #333)";
        row.appendChild(td);
      }
      table.appendChild(row);
    }
  }

  return table;
}

async function fetchRunStatus(runId) {
  const statusResponse = await api.fetchApi(
    "/workflowdirector/runs/" + encodeURIComponent(runId),
    { cache: "no-store" }
  );
  const statusBody = await statusResponse.json();

  if (!statusResponse.ok) {
    throw new Error(statusBody?.error ?? "HTTP " + statusResponse.status);
  }

  state.lastRunId = runId;
  state.lastRun = statusBody;
  refreshAllPanels();
  return statusBody;
}

async function refreshLastRun() {
  if (!state.lastRunId) {
    throw new Error("No WorkflowDirector run has been started in this tab.");
  }
  return await fetchRunStatus(state.lastRunId);
}

async function startRun(steps) {
  if (state.isRunning) {
    throw new Error("A WorkflowDirector lab run is already active.");
  }
  if (!steps.length || steps.some((step) => !step)) {
    throw new Error("Capture the required workflow slots first.");
  }

  state.isRunning = true;
  refreshAllPanels();

  try {
    const response = await api.fetchApi("/workflowdirector/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: api.clientId ?? null,
      steps,
    }),
  });

    const body = await response.json();
    if (!response.ok) {
      throw new Error(body?.error ?? "HTTP " + response.status);
    }

    state.lastRunId = body.run_id;
    state.lastRun = body;
    state.pollToken += 1;
    const token = state.pollToken;
    refreshAllPanels();
    notify("info", "WorkflowDirector run started", body.run_id);

    while (token === state.pollToken) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const statusBody = await fetchRunStatus(body.run_id);

      const phase = statusBody?.record?.phase;
      if (["completed", "failed", "cancelled"].includes(phase)) {
        state.isRunning = false;
        refreshAllPanels();
        notify(
          phase === "completed" ? "success" : "error",
          "WorkflowDirector run " + phase,
          statusBody?.record?.failure_detail ?? ""
        );
        return;
      }
    }
  } catch (error) {
    state.isRunning = false;
    refreshAllPanels();
    throw error;
  }
}

function button(label, handler, disabled = false) {
  const el = document.createElement("button");
  el.textContent = label;
  el.disabled = disabled;
  el.style.padding = "6px 10px";
  el.style.cursor = disabled ? "default" : "pointer";
  el.addEventListener("click", async () => {
    el.disabled = true;
    try {
      await handler();
    } catch (error) {
      console.error("[WorkflowDirector]", error);
      notify("error", "WorkflowDirector lab error", String(error));
    } finally {
      el.disabled = false;
      refreshAllPanels();
    }
  });
  return el;
}

const mountedPanels = new Set();

function renderPanel(root) {
  root.replaceChildren();
  root.style.padding = "10px";
  root.style.overflow = "auto";
  root.style.height = "100%";

  const warning = document.createElement("div");
  warning.textContent =
    "LAB ONLY — captures live only in this browser tab. Use fixed seeds and avoid nodes that depend on beforeQueued callbacks.";
  warning.style.fontWeight = "600";
  warning.style.marginBottom = "8px";
  root.appendChild(warning);

  const captures = document.createElement("div");
  captures.style.display = "flex";
  captures.style.gap = "8px";
  captures.style.flexWrap = "wrap";

  captures.appendChild(
    button("Capture current as A", () => capture("A"), state.isRunning)
  );
  captures.appendChild(
    button("Capture current as B", () => capture("B"), state.isRunning)
  );
  captures.appendChild(
    button(
      "Run A only",
      () => startRun([state.A]),
      !state.A || state.isRunning
    )
  );
  captures.appendChild(
    button(
      "Run A → B",
      () => startRun([state.A, state.B]),
      !state.A || !state.B || state.isRunning
    )
  );
  captures.appendChild(
    button(
      "Refresh last run",
      () => refreshLastRun(),
      !state.lastRunId || state.isRunning
    )
  );
  root.appendChild(captures);

  const slots = document.createElement("div");
  slots.style.margin = "8px 0";
  slots.textContent =
    "Browser-memory captures — A: " +
    (state.A ? state.A.workflow_id : "not captured") +
    " | B: " +
    (state.B ? state.B.workflow_id : "not captured");
  root.appendChild(slots);

  const run = state.lastRun;
  if (!run) return;

  const record = run.record ?? {};
  const status = document.createElement("div");
  status.style.marginTop = "8px";
  status.textContent =
    "Run " + (state.lastRunId ?? run.run_id ?? "?") +
    " — phase: " + (record.phase ?? "?") +
    (record.failure_code ? " — " + record.failure_code : "");
  root.appendChild(status);

  if (record.failure_detail) {
    const failure = document.createElement("pre");
    failure.textContent = record.failure_detail;
    failure.style.whiteSpace = "pre-wrap";
    root.appendChild(failure);
  }

  const summary = run.memory_summary;
  if (summary?.baseline_found) {
    const title = document.createElement("div");
    title.textContent =
      "Memory observations vs BASELINE (descriptive; not an unload verdict)";
    title.style.marginTop = "10px";
    title.style.fontWeight = "600";
    root.appendChild(title);
    root.appendChild(makeObservationTable(summary));
  }
}

function refreshAllPanels() {
  for (const panel of mountedPanels) renderPanel(panel);
}

app.registerExtension({
  name: "WorkflowDirector.Lab",
  bottomPanelTabs: [
    {
      id: "workflowdirector-lab",
      title: "Workflow Director Lab",
      type: "custom",
      render: (el) => {
        mountedPanels.add(el);
        renderPanel(el);
      },
    },
  ],
});
