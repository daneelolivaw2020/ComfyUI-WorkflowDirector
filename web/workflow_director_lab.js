import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const state = {
  A: null,
  B: null,
  C: null,
  // In-memory ordered workflow list. IDs remain stable when rows move.
  sequence: [],
  nextSequenceId: 1,
  sequenceSelectedPath: null,
  sequenceEditing: false,
  sequenceRevision: 0,
  sequenceRunRevision: null,
  sequenceRunId: null,
  legacyExpanded: false,
  lastRunId: null,
  lastRun: null,
  pollToken: 0,
  isRunning: false,
  autoRefresh: true,
  followActive: true,
  stepNotifications: true,
  currentSteps: [],
  announcedEvents: new Set(),
  monitoringUncertain: false,
  statusWarning: "",
  liveContext: null,
  syncedRunId: null,
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

async function prepareCurrentSteps(slots, { allowRepeats = false } = {}) {
  if (!state.autoRefresh) {
    // Manual mode is deliberately explicit: do not mutate captures.
    return slots.map((slot) => ({ ...slot }));
  }
  const previousTab = selectedWorkflowTab();
  const previousPath = previousTab.dataset.workflowPath;
  const previousId = assertCompiled(await app.graphToPrompt()).workflow.id;
  const workflowIds = slots.map((s) => s.workflow_id);
  if (!allowRepeats && new Set(workflowIds).size !== workflowIds.length) {
    throw new Error(
      "Two linked tabs share a workflow UUID. Make each workflow a separate " +
      "document with a unique UUID, then capture the slots again. No run was submitted."
    );
  }
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
    if (!restore) {
      throw new Error(
        "The original workflow tab was closed during preparation. " +
        "No run was submitted."
      );
    }
    // Wait for the *canvas*, not only the highlighted tab, to match the
    // original view before the prepared jobs may be submitted.
    await openTabAndCompile(previousPath, previousId);
  }
  return prepared;
}

const PUT_NODE_PREFIX = "WorkflowDirectorContextPut";

function plannedContextKeys() {
  // The live Context is empty before the Director starts. Offer keys from
  // linked producers as choices for configuring GET before A has run.
  const keys = new Set();
  for (const step of [state.A, state.B, ...state.sequence, ...state.currentSteps]) {
    const prompt = step?.prompt ?? {};
    for (const node of Object.values(prompt)) {
      if (!node?.class_type?.startsWith(PUT_NODE_PREFIX)) continue;
      const key = node?.inputs?.key;
      if (typeof key === "string" && key.trim() === key && key) keys.add(key);
    }
  }
  return [...keys].sort();
}

function availableContextKeys() {
  return [...new Set([
    ...plannedContextKeys(),
    ...Object.keys(state.liveContext?.committed ?? {}),
    ...Object.keys(state.lastRun?.record?.context_manifest ?? {}),
  ])].sort();
}

async function inspectLiveContext() {
  const response = await api.fetchApi("/workflowdirector/context", { cache: "no-store" });
  if (!response.ok) throw new Error("Context inspection HTTP " + response.status);
  state.liveContext = await response.json();
  refreshAllPanels();
  return state.liveContext;
}

function describeShape(shape) {
  if (!shape || typeof shape !== "object") return "";
  if (shape.kind === "tensor") {
    return "Tensor [" + (shape.shape ?? []).join("×") + "] " + (shape.dtype ?? "");
  }
  if (shape.kind === "dict") {
    return "dict {" + Object.keys(shape.fields ?? {}).join(", ") +
      (shape.truncated ? ", …" : "") + "}";
  }
  if (shape.kind === "list" || shape.kind === "tuple") {
    return shape.kind + " (" + shape.length + " elements)";
  }
  return String(shape.kind ?? "");
}

async function synchronizeTerminalOutputs(run) {
  // Comfy's executed websocket handler resolves node IDs against the currently
  // mounted canvas. Fast A→B jobs can finish before the Lab switches tabs.
  // Recover the canonical output metadata from /history after native success.
  if (!state.followActive || run?.record?.phase !== "completed") return;
  const runId = run?.run_id ?? state.lastRunId;
  if (!runId || state.syncedRunId === runId) return;
  const attempts = run.record.attempts ?? [];
  const last = attempts[attempts.length - 1];
  if (!last || last.state !== "completed" || !last.job_id) return;
  const step = state.currentSteps.find((x) => x.step_id === last.step_id);
  if (!step?.tab_path || !findWorkflowTab(step.tab_path)) return;
  await restoreOutputFromHistory(step, last.job_id);
  state.syncedRunId = runId;
}

async function restoreOutputFromHistory(step, jobId) {
  if (!findWorkflowTab(step.tab_path)) {
    throw new Error("The workflow tab is closed. Reopen it to view outputs.");
  }
  const response = await api.fetchApi(
    "/history/" + encodeURIComponent(jobId), { cache: "no-store" }
  );
  if (!response.ok) throw new Error("Comfy history HTTP " + response.status);
  const history = await response.json();
  const result = history?.[jobId];
  if (!result || result?.status?.status_str !== "success") {
    throw new Error("Native history not yet available for completed job " + jobId);
  }
  // Never apply output IDs from B to the canvas for A (or another workflow).
  await openTabAndCompile(step.tab_path, step.workflow_id);
  const outputs = result.outputs ?? {};
  app.nodeOutputs = outputs;
  for (const [id, output] of Object.entries(outputs)) {
    const node = app.graph?.getNodeById?.(Number(id));
    if (node?.onExecuted) node.onExecuted(output);
  }
  app.canvas?.setDirty?.(true, true);
}

async function viewSequenceResult(step) {
  if (state.isRunning || state.monitoringUncertain || state.sequenceEditing) {
    throw new Error("Wait until the current run finishes.");
  }
  if (state.sequenceRunRevision !== state.sequenceRevision ||
      !state.sequenceRunId || state.sequenceRunId !== state.lastRunId ||
      state.lastRun?.run_id !== state.sequenceRunId) {
    throw new Error("The sequence changed since the last run.");
  }
  const compiledStep = state.currentSteps.find(s => s.step_id === step.step_id);
  const attempt = state.lastRun.record?.attempts?.find(a => a.step_id === step.step_id);
  if (!compiledStep || !attempt || attempt.state !== "completed" ||
      compiledStep.workflow_id !== step.workflow_id ||
      compiledStep.tab_path !== step.tab_path) {
    throw new Error("This workflow has no completed native job in the last run.");
  }
  await restoreOutputFromHistory(compiledStep, attempt.job_id);
}

async function safelySynchronizeOutputs(run) {
  try {
    await synchronizeTerminalOutputs(run);
  } catch (error) {
    // Presentation must never overwrite the successful Director run state.
    console.warn("[WorkflowDirector] Could not restore visual outputs", error);
    notify("warn", "Workflow results available in history",
      "The native job completed, but the visible node outputs were not restored.");
  }
}

function attachGetKeySelector(node) {
  if (!node?.addWidget || !node.widgets) return;
  // Show a nonfatal warning when GET returns None for a missing Context key.
  // Keep normal node output processing intact for ComfyUI's own widgets.
  if (!node.__wdContextWarningInstalled) {
    const originalOnExecuted = node.onExecuted;
    node.onExecuted = function (output, ...args) {
      const result = originalOnExecuted?.call(this, output, ...args);
      for (const message of output?.text ?? []) {
        if (typeof message !== "string" ||
            !message.startsWith("WD_CONTEXT_MISSING:")) continue;
        const key = message.slice("WD_CONTEXT_MISSING:".length);
        notify("warn", "Context key unavailable",
          "'" + key + "' is not in this run. GET returned None; a connected " +
          "Any Switch can use the fallback input.");
      }
      return result;
    };
    node.__wdContextWarningInstalled = true;
  }
  const keyWidget = node.widgets.find((widget) => widget.name === "key");
  if (!keyWidget || node.widgets.some((widget) => widget.name === "context_key_picker")) return;
  const empty = "Choose Context key…";
  // Comfy frontend graphToPrompt checks widget.options.serialize, whereas
  // LiteGraph workflow persistence checks widget.serialize separately.
  const options = { serialize: false };
  Object.defineProperty(options, "values", {
    enumerable: true,
    get: () => [empty, ...availableContextKeys()],
  });
  const picker = node.addWidget("combo", "context_key_picker", empty, (chosen) => {
    if (!chosen || chosen === empty) return;
    keyWidget.value = chosen;
    node.setDirtyCanvas?.(true, true);
    app.graph?.change?.();
  }, options);
  // Selector is UI convenience only; the original 'key' remains the sole API
  // input and can be typed/linked manually. Never put ephemeral combo state
  // into Comfy's API prompt.
  picker.serialize = false;
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
  const conflicting = ["A", "B", "C"].filter((other) => other !== slot)
    .find((other) => state[other]?.tab_path === path ||
      state[other]?.workflow_id === frozen.workflow.id);
  if (conflicting) {
    throw new Error("Workflow " + slot + " shares a tab or UUID with " +
      conflicting + ". Use independent workflow documents.");
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

function sequenceEditable() {
  return !state.isRunning && !state.monitoringUncertain && !state.sequenceEditing;
}

function sequenceChanged() {
  state.sequenceRevision += 1;
  state.sequenceRunRevision = null;
  state.sequenceRunId = null;
  refreshAllPanels();
}

async function addSequenceTab(path) {
  if (!sequenceEditable()) {
    throw new Error("Wait for the current run or capture to finish.");
  }

  // Capture ONLY the currently loaded tab. Automatically switching to an
  // arbitrary tab risks capturing the previous canvas before its asynchronous
  // load has finished, without having a trusted expected UUID to compare.
  const active = selectedWorkflowTab();
  if (active.dataset.workflowPath !== path) {
    throw new Error("Select the workflow in the ComfyUI top bar before adding it.");
  }
  state.sequenceEditing = true;
  refreshAllPanels();
  try {
    // A short settle plus two consistent compilations avoids common
    // selected-tab-change races without guessing from a tab display name.
    await sleep(100);
    const current = selectedWorkflowTab();
    if (current.dataset.workflowPath !== path) {
      throw new Error("Workflow tab changed during capture. Nothing was added.");
    }
    const first = snapshotCompiled(assertCompiled(await app.graphToPrompt()));
    await sleep(100);
    const second = snapshotCompiled(assertCompiled(await app.graphToPrompt()));
    if (selectedWorkflowTab().dataset.workflowPath !== path ||
        first.workflow.id !== second.workflow.id) {
      throw new Error("The selected workflow canvas was still loading. Retry Add.");
    }
    const stepId = "W" + state.nextSequenceId++;
    state.sequence.push({
      step_id: stepId,
      workflow_id: second.workflow.id,
      name: tabName(current),
      tab_path: path,
      prompt: second.output,
      workflow: second.workflow,
    });
    sequenceChanged();
    notify("success", "Workflow added to sequence", tabName(current));
  } finally {
    state.sequenceEditing = false;
    refreshAllPanels();
  }
}

function moveSequenceStep(index, delta) {
  if (!sequenceEditable()) throw new Error("Cannot reorder during a run.");
  const next = index + delta;
  if (index < 0 || index >= state.sequence.length ||
      next < 0 || next >= state.sequence.length) return;
  [state.sequence[index], state.sequence[next]] =
    [state.sequence[next], state.sequence[index]];
  sequenceChanged();
}

function removeSequenceStep(index) {
  if (!sequenceEditable()) throw new Error("Cannot remove during a run.");
  if (index < 0 || index >= state.sequence.length) return;
  state.sequence.splice(index, 1);
  sequenceChanged();
}

async function runSequence() {
  if (!state.sequence.length) {
    throw new Error("Add at least one workflow to the sequence.");
  }
  state.sequenceRunRevision = state.sequenceRevision;
  state.sequenceRunId = null;
  return startRun([...state.sequence], {
    allowRepeats: true,
    source: "sequence",
  });
}

async function runSequenceStep(step) {
  if (!state.sequence.includes(step)) {
    throw new Error("This workflow is no longer in the sequence.");
  }
  state.sequenceRunRevision = state.sequenceRevision;
  state.sequenceRunId = null;
  return startRun([step], { allowRepeats: true, source: "sequence" });
}

function sequenceStepStatus(step) {
  if (state.sequenceRunRevision !== state.sequenceRevision ||
      !state.sequenceRunId || state.lastRunId !== state.sequenceRunId ||
      state.lastRun?.run_id !== state.sequenceRunId) return "Not run";
  const record = state.lastRun.record ?? {};
  const attempt = (record.attempts ?? []).find(a => a.step_id === step.step_id);
  if (attempt) {
    const name = attempt.state;
    if (name === "completed") return "Completed";
    if (name === "failed") return "Failed";
    if (name === "cancelled") return "Cancelled";
    if (name === "in_progress") return "Running";
    return "Queued";
  }
  if (record.phase === "running" || record.phase === "ready") return "Waiting";
  return "Not reached";
}

function sequenceButton(label, action, disabled) {
  const node = button(label, action, disabled);
  node.style.padding = "4px 8px";
  return node;
}

function renderSequence(root) {
  const section = document.createElement("section");
  section.style.border = "1px solid var(--border-color, #555)";
  section.style.borderRadius = "9px";
  section.style.padding = "12px";
  section.style.marginBottom = "10px";

  const heading = document.createElement("div");
  heading.textContent = "Workflow sequence";
  heading.style.fontWeight = "700";
  heading.style.fontSize = "16px";
  section.appendChild(heading);

  const summary = document.createElement("div");
  summary.style.fontSize = "12px";
  summary.style.opacity = "0.85";
  summary.style.margin = "3px 0 10px";
  summary.textContent =
    "Arrange normal ComfyUI workflows in execution order. " +
    "Context survives between steps of this run; it is released at the end. " +
    "This list is temporary (not saved). Cleanup is not inserted automatically.";
  section.appendChild(summary);

  const controls = document.createElement("div");
  controls.style.display = "flex";
  controls.style.flexWrap = "wrap";
  controls.style.gap = "7px";

  const activeTab = (() => {
    try { return selectedWorkflowTab(); } catch { return null; }
  })();
  const selectedLabel = document.createElement("span");
  selectedLabel.style.flex = "1";
  selectedLabel.style.minWidth = "170px";
  selectedLabel.style.fontSize = "12px";
  selectedLabel.style.alignSelf = "center";
  selectedLabel.textContent = activeTab
    ? "Current ComfyUI tab: " + tabName(activeTab)
    : "Select a workflow in the ComfyUI top bar";
  controls.appendChild(selectedLabel);
  controls.appendChild(
    sequenceButton("+ Add current workflow",
      () => addSequenceTab(selectedWorkflowTab().dataset.workflowPath),
      !sequenceEditable() || !activeTab)
  );
  controls.appendChild(
    sequenceButton("Run all (" + state.sequence.length + ")",
      () => runSequence(),
      !sequenceEditable() || !state.sequence.length)
  );
  section.appendChild(controls);

  const list = document.createElement("div");
  list.style.display = "grid";
  list.style.gap = "5px";
  list.style.marginTop = "12px";
  if (!state.sequence.length) {
    const hint = document.createElement("div");
    hint.style.opacity = "0.7";
    hint.textContent = "No workflows yet. Select an open tab and click + Add workflow.";
    list.appendChild(hint);
  }
  for (const [index, step] of state.sequence.entries()) {
    const row = document.createElement("div");
    row.style.display = "flex";
    row.style.alignItems = "center";
    row.style.gap = "7px";
    row.style.border = "1px solid var(--border-color, #555)";
    row.style.borderRadius = "6px";
    row.style.padding = "6px 8px";

    const num = document.createElement("strong");
    num.textContent = (index + 1) + ".";
    num.style.minWidth = "22px";
    row.appendChild(num);

    const label = document.createElement("div");
    label.style.flex = "1";
    label.style.minWidth = "100px";
    const actualTab = findWorkflowTab(step.tab_path);
    const title = document.createElement("div");
    title.textContent = actualTab ? tabName(actualTab) : step.name + " (closed)";
    title.style.fontWeight = "600";
    label.appendChild(title);
    const info = document.createElement("div");
    info.style.fontSize = "11px";
    info.style.opacity = "0.75";
    info.textContent = step.step_id + " · " +
      (actualTab ? sequenceStepStatus(step) : "Tab closed");
    label.appendChild(info);
    row.appendChild(label);

    if (actualTab) {
      row.appendChild(sequenceButton("Open", () => {
        if (state.isRunning || state.sequenceEditing) {
          throw new Error("Cannot switch while the Director is running.");
        }
        (actualTab.querySelector(".workflow-label") || actualTab).click();
      }, state.isRunning || state.sequenceEditing));
    }
    row.appendChild(sequenceButton("Run only",
      () => runSequenceStep(step),
      !actualTab || !sequenceEditable()));
    row.appendChild(sequenceButton("View result",
      () => viewSequenceResult(step),
      !actualTab || !sequenceEditable() ||
      sequenceStepStatus(step) !== "Completed"));

    row.appendChild(sequenceButton("↑",
      () => moveSequenceStep(index, -1),
      !sequenceEditable() || index === 0));
    row.appendChild(sequenceButton("↓",
      () => moveSequenceStep(index, 1),
      !sequenceEditable() || index === state.sequence.length - 1));
    row.appendChild(sequenceButton("Remove",
      () => removeSequenceStep(index), !sequenceEditable()));
    list.appendChild(row);
  }
  section.appendChild(list);
  root.appendChild(section);
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
    "Anon PSS",
    "Δ anon",
    "File PSS",
    "Δ file",
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
      metricValue(baselineMetrics, "process_pss_anon_gib"),
      deltaValue(baselineMetrics, "process_pss_anon_gib"),
      metricValue(baselineMetrics, "process_pss_file_gib"),
      deltaValue(baselineMetrics, "process_pss_file_gib"),
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
        metricValue(metrics, "process_pss_anon_gib"),
        deltaValue(metrics, "process_pss_anon_gib"),
        metricValue(metrics, "process_pss_file_gib"),
        deltaValue(metrics, "process_pss_file_gib"),
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
  if (["completed", "failed", "cancelled"].includes(statusBody?.record?.phase)) {
    state.monitoringUncertain = false;
    state.statusWarning = "";
  }
  announceStepEvents(statusBody);
  // Best effort: metadata only, while this run owns Context.
  if (statusBody?.record?.phase === "running") {
    try { await inspectLiveContext(); } catch (error) {
      console.warn("[WorkflowDirector] Context inspector unavailable", error);
    }
  }
  refreshAllPanels();
  return statusBody;
}

async function refreshLastRun() {
  if (!state.lastRunId) {
    throw new Error("No WorkflowDirector run has been started in this tab.");
  }
  const result = await fetchRunStatus(state.lastRunId);
  if (result?.record?.phase === "completed") {
    await safelySynchronizeOutputs(result);
  }
  if (!["completed", "failed", "cancelled"].includes(result?.record?.phase)) {
    state.statusWarning =
      "The backend run is still active or not terminal. Do not start another run.";
    refreshAllPanels();
  }
  return result;
}

async function startRun(steps, { allowRepeats = false, source = "legacy" } = {}) {
  if (state.isRunning || state.monitoringUncertain) {
    throw new Error(
      "A WorkflowDirector run may still be active. Reconnect to the last run " +
      "with Refresh last run before submitting a new one."
    );
  }
  if (!steps.length || steps.some((step) => !step)) {
    throw new Error("Capture the required workflow slots first.");
  }

  state.isRunning = true;
  refreshAllPanels();

  let requestSent = false;
  let acknowledged = false;
  let rejected = false;
  try {
    const preparedSteps = await prepareCurrentSteps(steps, { allowRepeats });
    state.currentSteps = preparedSteps;
    state.syncedRunId = null;
    state.liveContext = null;
    state.announcedEvents = new Set();
    state.statusWarning = "";
    // Preassign and retain the run UUID before submission so a lost HTTP
    // acknowledgement can be reconciled by GET /runs/{run_id}.
    const runId = crypto.randomUUID();
    if (source === "sequence") state.sequenceRunId = runId;
    const responsePromise = api.fetchApi("/workflowdirector/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      client_id: api.clientId ?? null,
      steps: preparedSteps.map(({ tab_path, ...step }) => step),
    }),
  });
    requestSent = true;
    state.lastRunId = runId;
    const response = await responsePromise;
    if (!response.ok) {
      rejected = true; // HTTP non-202 is an explicit backend rejection.
      throw new Error("HTTP " + response.status + " — request rejected");
    }
    const body = await response.json();
    if (body?.run_id !== runId) {
      throw new Error("Run acknowledgement ID mismatch");
    }
    acknowledged = true;

    state.lastRunId = body.run_id;
    state.lastRun = body;
    state.pollToken += 1;
    const token = state.pollToken;
    refreshAllPanels();
    notify("info", "WorkflowDirector run started", body.run_id);

    let consecutiveFailures = 0;
    while (token === state.pollToken) {
      await sleep(500);
      let statusBody;
      try {
        statusBody = await fetchRunStatus(body.run_id);
        consecutiveFailures = 0;
      } catch (pollError) {
        consecutiveFailures += 1;
        if (consecutiveFailures === 3) {
          notify(
            "warn",
            "WorkflowDirector temporarily disconnected",
            "Backend run may still be running; retrying status checks."
          );
        }
        if (consecutiveFailures >= 12) {
          state.monitoringUncertain = true;
          state.statusWarning =
            "Connection to the run was lost. Its backend execution may still " +
            "be active. Use Refresh last run to reconcile; no new run is allowed.";
          state.isRunning = false;
          refreshAllPanels();
          notify("error", "WorkflowDirector status uncertain", state.statusWarning);
          return;
        }
        continue;
      }

      const phase = statusBody?.record?.phase;
      if (["completed", "failed", "cancelled"].includes(phase)) {
        if (phase === "completed") await safelySynchronizeOutputs(statusBody);
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
    if (requestSent && !acknowledged && !rejected) {
      state.monitoringUncertain = true;
      state.statusWarning =
        "Run submission acknowledgement was lost or invalid. The backend " +
        "might still be executing it. Use Refresh last run to check its UUID. " +
        "Do not submit another run.";
    }
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

  renderSequence(root);

  const legacy = document.createElement("details");
  legacy.open = state.legacyExpanded;
  legacy.addEventListener("toggle", () => {
    if (root.contains(legacy)) state.legacyExpanded = legacy.open;
  });
  const legacyTitle = document.createElement("summary");
  legacyTitle.textContent = "Legacy A / B / Cleanup lab controls";
  legacyTitle.style.cursor = "pointer";
  legacyTitle.style.opacity = "0.8";
  legacyTitle.style.marginBottom = "5px";
  legacy.appendChild(legacyTitle);
  root.appendChild(legacy);

  const warning = document.createElement("div");
  warning.textContent =
    "LAB ONLY — bind two or three OPEN TOPBAR workflow tabs. Fresh compile before each Run (optional); immutable during the run. Cleanup C is opt-in. Use fixed seeds; beforeQueued-dependent nodes remain experimental.";
  warning.style.fontWeight = "600";
  warning.style.marginBottom = "8px";
  legacy.appendChild(warning);

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
    button("Capture current as Cleanup", () => capture("C"), state.isRunning)
  );
  captures.appendChild(
    button(
      "Run A only",
      () => startRun([state.A]),
      !state.A || state.isRunning || state.monitoringUncertain
    )
  );
  captures.appendChild(
    button(
      "Run B only",
      () => startRun([state.B]),
      !state.B || state.isRunning || state.monitoringUncertain
    )
  );
  captures.appendChild(
    button(
      "Run A → B",
      () => startRun([state.A, state.B]),
      !state.A || !state.B || state.isRunning || state.monitoringUncertain
    )
  );
  captures.appendChild(
    button(
      "Run A → Cleanup → B",
      () => startRun([state.A, state.C, state.B]),
      !state.A || !state.C || !state.B || state.isRunning || state.monitoringUncertain
    )
  );
  captures.appendChild(
    button(
      "Refresh last run",
      () => refreshLastRun(),
      !state.lastRunId || state.isRunning
    )
  );
  legacy.appendChild(captures);

  const standaloneNotice = document.createElement("div");
  standaloneNotice.textContent =
    "Run B only cannot read A from a previous run. Optional Cleanup (C) " +
    "runs as an independent native job AFTER A commits Context and BEFORE B; " +
    "use an already proven cleanup workflow. C must not contain Context nodes.";
  standaloneNotice.style.fontSize = "12px";
  standaloneNotice.style.marginTop = "6px";
  legacy.appendChild(standaloneNotice);

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
  legacy.appendChild(options);

  const slots = document.createElement("div");
  slots.style.margin = "8px 0";
  slots.textContent =
    "Linked tabs (browser memory) — A: " +
    (state.A ? state.A.name + " [" + state.A.workflow_id + "]" : "not linked") +
    " | B: " +
    (state.B ? state.B.name + " [" + state.B.workflow_id + "]" : "not linked") +
    " | Cleanup: " +
    (state.C ? state.C.name + " [" + state.C.workflow_id + "]" : "not linked") +
    (state.autoRefresh ? " | compiled fresh before each Run" : " | manual snapshots");
  legacy.appendChild(slots);
  if (state.statusWarning) {
    const warning = document.createElement("div");
    warning.textContent = state.statusWarning;
    warning.style.color = "var(--error-color, #cf534a)";
    warning.style.fontWeight = "600";
    legacy.appendChild(warning);
  }

  const run = state.lastRun ?? { record: {} };

  const record = run.record ?? {};
  if (state.lastRun) {
    const status = document.createElement("div");
    status.style.marginTop = "8px";
    status.textContent =
      "Run " + (state.lastRunId ?? run.run_id ?? "?") +
      " — phase: " + (record.phase ?? "?") +
      (record.failure_code ? " — " + record.failure_code : "");
    root.appendChild(status);
  }

  if (record.failure_detail) {
    const failure = document.createElement("pre");
    failure.textContent = record.failure_detail;
    failure.style.whiteSpace = "pre-wrap";
    root.appendChild(failure);
  }

  const committedContext = record.context_manifest ?? {};

  const explorerTitle = document.createElement("div");
  explorerTitle.textContent = "Context explorer · metadata only";
  explorerTitle.style.marginTop = "12px";
  explorerTitle.style.fontWeight = "600";
  root.appendChild(explorerTitle);
  const help = document.createElement("div");
  help.style.fontSize = "12px";
  help.textContent = "Planned keys come from linked PUT nodes; committed keys from " +
    "the active run or last run snapshot. Values are never exposed. " +
    "Completed runs release their Context.";
  root.appendChild(help);
  const contextActions = document.createElement("div");
  contextActions.style.margin = "6px 0";
  contextActions.appendChild(
    button("Refresh live Context", () => inspectLiveContext())
  );
  root.appendChild(contextActions);
  const planned = new Set(plannedContextKeys());
  const live = state.liveContext?.active
    ? state.liveContext.committed ?? {} : {};
  const last = record.context_inspection ?? {};
  const keys = availableContextKeys();
  if (!keys.length) {
    const empty = document.createElement("div");
    empty.textContent = "No Context keys found yet. Link a workflow containing PUT.";
    empty.style.fontSize = "12px";
    root.appendChild(empty);
  } else {
    const explorer = document.createElement("table");
    explorer.style.width = "100%";
    explorer.style.fontSize = "12px";
    for (const key of keys) {
      const meta = live[key] ?? last[key] ?? committedContext[key];
      const phase = live[key] ? "LIVE committed" :
        committedContext[key] ? "Last run (released)" :
        planned.has(key) ? "Planned by PUT" : "Unknown";
      const row = document.createElement("tr");
      const fields = [key, phase,
        meta ? (meta.type + " · " + meta.bytes + " bytes") : "",
        describeShape(meta?.shape)];
      for (const value of fields) {
        const cell = document.createElement("td");
        cell.textContent = value;
        cell.style.padding = "4px 7px";
        row.appendChild(cell);
      }
      explorer.appendChild(row);
    }
    root.appendChild(explorer);
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
  name: "WorkflowDirector.ContextKeyPicker",
  nodeCreated(node) {
    if (node?.comfyClass === "WorkflowDirectorContextGetUniversal" ||
        node?.type === "WorkflowDirectorContextGetUniversal") {
      attachGetKeySelector(node);
    }
  },
});

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
