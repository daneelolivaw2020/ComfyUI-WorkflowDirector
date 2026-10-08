import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const state = {
  A: null,
  B: null,
  lastRunId: null,
  lastRun: null,
  pollToken: 0,
  isRunning: false,
  autoRefresh: true,
  followActive: true,
  stepNotifications: true,
  currentSteps: [],
  announcedEvents: new Set(),
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


const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/*
 * ComfyUI frontend 1.53.10: the top-bar WorkflowTab exposes a stable
 * data-workflow-path, and SelectButton marks its active option.
 * Do not guess a workflow from its display name or silently reuse an old
 * captured prompt when the associated tab is missing.
 */
function workflowTabs() {
  return [...document.querySelectorAll(".workflow-tabs-container [data-workflow-path]")];
}

function selectedWorkflowTab() {
  const selected = workflowTabs().filter((tab) => {
    let el = tab;
    for (let depth = 0; el && depth < 5; depth++, el = el.parentElement) {
      if (
        el.getAttribute("aria-pressed") === "true" ||
        el.getAttribute("aria-selected") === "true" ||
        el.getAttribute("data-p-active") === "true" ||
        el.classList?.contains("p-togglebutton-checked") ||
        el.classList?.contains("p-highlight")
      ) {
        return true;
      }
    }
    return false;
  });
  if (selected.length !== 1) {
    throw new Error(
      "Cannot identify exactly one active workflow tab. " +
      "In ComfyUI Settings, set Workflow Tabs Position to Topbar; " +
      "then select the workflow tab and retry. No stale capture was executed."
    );
  }
  return selected[0];
}

function findWorkflowTab(path) {
  return workflowTabs().find((tab) => tab.dataset.workflowPath === path) ?? null;
}

function tabName(tab) {
  return tab?.querySelector(".workflow-label")?.textContent?.trim()
    || tab?.dataset.workflowPath?.split("/").pop()
    || "Unnamed workflow";
}

function assertCompiled(compiled, expectedId = null) {
  const workflowId = compiled?.workflow?.id;
  if (typeof workflowId !== "string" || !workflowId || !compiled?.output) {
    throw new Error("ComfyUI did not return a valid compiled workflow and API prompt.");
  }
  if (expectedId && workflowId !== expectedId) {
    throw new Error(
      "Workflow tab identity changed: expected " + expectedId +
      ", received " + workflowId + ". Recapture explicitly."
    );
  }
  return compiled;
}

async function openTabAndCompile(path, expectedId) {
  const tab = findWorkflowTab(path);
  if (!tab) {
    throw new Error(
      "Registered workflow tab " + path +
      " is closed or missing. Reopen it and capture that slot again."
    );
  }
  if (selectedWorkflowTab().dataset.workflowPath !== path) {
    (tab.querySelector(".workflow-label") || tab).click();
  }

  // The frontend tab selection and app.loadGraphData() are asynchronous.
  // Never capture from the previous canvas while the new tab is loading.
  const deadline = Date.now() + 12000;
  let lastId = null;
  while (Date.now() < deadline) {
    const active = selectedWorkflowTab();
    if (active.dataset.workflowPath === path) {
      const compiled = await app.graphToPrompt();
      lastId = compiled?.workflow?.id;
      if (lastId === expectedId) {
        return { compiled: snapshotCompiled(assertCompiled(compiled, expectedId)), tab: active };
      }
    }
    await sleep(150);
  }
  throw new Error(
    "Could not verify that ComfyUI loaded the expected canvas for " +
    path + ". Expected workflow id " + expectedId +
    ", observed " + (lastId ?? "none") +
    ". No run was submitted."
  );
}

async function prepareCurrentSteps(slots) {
  if (!state.autoRefresh) {
    // Manual mode is deliberately explicit: do not mutate captures.
    return slots.map((slot) => ({ ...slot }));
  }
  const previousTab = selectedWorkflowTab();
  const previousPath = previousTab.dataset.workflowPath;
  const prepared = [];
  try {
    for (const slot of slots) {
      if (!slot.tab_path) {
        throw new Error("Capture " + slot.step_id + " again to bind its tab.");
      }
      const { compiled, tab } = await openTabAndCompile(slot.tab_path, slot.workflow_id);
      prepared.push({
        step_id: slot.step_id,
        workflow_id: slot.workflow_id,
        name: tabName(tab),
        prompt: compiled.output,
        workflow: compiled.workflow,
        tab_path: slot.tab_path,
      });
    }
  } finally {
    // The run snapshot is independent of the visible tab. Restore the user's
    // original view even on failure; the per-step follow option handles
    // navigation once a native job actually begins.
    const restore = findWorkflowTab(previousPath);
    if (restore && selectedWorkflowTab().dataset.workflowPath !== previousPath) {
      (restore.querySelector(".workflow-label") || restore).click();
    }
  }
  return prepared;
}

function announceStepEvents(run) {
  if (!state.lastRunId || !state.currentSteps.length) return;
  const events = run?.record?.events ?? [];
  for (const event of events) {
    const kind = event.kind;
    const step = state.currentSteps.find((s) => s.step_id === event.step_id);
    if (!step) continue;
    const stageKey = state.lastRunId + ":" + kind + ":" +
      (event.job_id ?? "") + ":" + step.step_id + ":" + (event.detail ?? "");
    if (state.announcedEvents.has(stageKey)) continue;
    state.announcedEvents.add(stageKey);
    if (kind === "job_state" && event.detail === "in_progress") {
      if (state.stepNotifications) {
        notify("info", "Workflow " + step.step_id + " running", step.name);
      }
      if (state.followActive && step.tab_path) {
        const tab = findWorkflowTab(step.tab_path);
        if (tab) {
          (tab.querySelector(".workflow-label") || tab).click();
        } else {
          notify("warn", "Workflow tab not found", step.name);
        }
      }
    }
    if (kind === "boundary_completed" && state.stepNotifications) {
      notify("success", "Workflow " + step.step_id + " completed", step.name);
    }
  }
}

async function capture(slot) {
  if (state.isRunning) throw new Error("Cannot capture during a Director run.");
  const activeTab = selectedWorkflowTab();
  const frozen = snapshotCompiled(assertCompiled(await app.graphToPrompt()));
  const path = activeTab.dataset.workflowPath;
  const otherSlot = slot === "A" ? "B" : "A";
  if (state[otherSlot]?.tab_path === path) {
    throw new Error("A and B must refer to different workflow tabs.");
  }

  state[slot] = {
    step_id: slot,
    workflow_id: frozen.workflow.id,
    name: tabName(activeTab),
    tab_path: path,
    prompt: frozen.output,
    workflow: frozen.workflow,
  };

  notify("success", "Workflow " + slot + " linked", state[slot].name);
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
  announceStepEvents(statusBody);
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
    const preparedSteps = await prepareCurrentSteps(steps);
    state.currentSteps = preparedSteps;
    state.announcedEvents = new Set();
    const response = await api.fetchApi("/workflowdirector/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: api.clientId ?? null,
      steps: preparedSteps.map(({ tab_path, ...step }) => step),
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
    "LAB ONLY — bind two OPEN TOPBAR workflow tabs. Fresh compile before each Run (optional); immutable during the run. Use fixed seeds; beforeQueued-dependent nodes remain experimental.";
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

  const options = document.createElement("div");
  options.style.display = "flex";
  options.style.gap = "14px";
  options.style.flexWrap = "wrap";
  options.style.marginTop = "10px";
  for (const [key, text] of [
    ["autoRefresh", "Refresh linked tabs before Run"],
    ["followActive", "Show executing workflow tab"],
    ["stepNotifications", "Notify on each workflow"],
  ]) {
    const label = document.createElement("label");
    label.style.display = "flex";
    label.style.gap = "5px";
    label.style.alignItems = "center";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state[key];
    checkbox.disabled = state.isRunning;
    checkbox.addEventListener("change", () => { state[key] = checkbox.checked; });
    label.append(checkbox, document.createTextNode(text));
    options.appendChild(label);
  }
  root.appendChild(options);

  const slots = document.createElement("div");
  slots.style.margin = "8px 0";
  slots.textContent =
    "Linked tabs (browser memory) — A: " +
    (state.A ? state.A.name + " [" + state.A.workflow_id + "]" : "not linked") +
    " | B: " +
    (state.B ? state.B.name + " [" + state.B.workflow_id + "]" : "not linked") +
    (state.autoRefresh ? " | compiled fresh before each Run" : " | manual snapshots");
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
