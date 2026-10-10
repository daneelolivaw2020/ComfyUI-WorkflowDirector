/* Tests for the WorkflowDirector Lab browser controller without a Comfy backend.
 * Run: node --test tests/lab_ui.test.cjs
 * These exercise snapshot binding, fresh compilation, fail-closed behavior and
 * per-stage UI events with simulated frontend tabs. Real Colab UI still needs
 * manual acceptance testing.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("web/workflow_director_lab.js", "utf8")
  .replace(/^import \{.*\} from .*;\s*$/gm, "") +
  "\nglobalThis.__lab = { state, capture, prepareCurrentSteps, " +
  "openTabAndCompile, selectedWorkflowTab, announceStepEvents, startRun, " +
  "availableContextKeys, plannedContextKeys, attachGetKeySelector, synchronizeTerminalOutputs, " +
  "addSequenceTab, moveSequenceStep, removeSequenceStep, runSequence, runSequenceStep, sequenceStepStatus, viewSequenceResult };";

function makeEnvironment(config = {}) {
  const tabs = new Map();
  const toasts = [];
  const extensions = [];
  let activePath = null;

  function makeTab(path, name, id, seed = 1) {
    const tab = {
      dataset: { workflowPath: path },
      id, name, seed,
      parentElement: null,
      getAttribute() { return null; },
      classList: { contains() { return false; } },
      querySelector(selector) {
        if (selector !== ".workflow-label") return null;
        return { textContent: this.name, click: () => { activePath = path; } };
      },
      click() { activePath = path; },
    };
    const ancestor = {
      parentElement: null,
      getAttribute(attr) {
        return attr === "aria-pressed" && activePath === path ? "true" : null;
      },
      classList: { contains() { return false; } },
    };
    tab.parentElement = ancestor;
    tabs.set(path, tab);
    if (activePath == null) activePath = path;
    return tab;
  }

  const app = {
    extensionManager: { toast: { add: (entry) => toasts.push(entry) } },
    registerExtension(extension) { extensions.push(extension); },
    async graphToPrompt() {
      const tab = tabs.get(activePath);
      if (!tab) throw new Error("tab missing");
      return {
        workflow: { id: tab.id, seed: tab.seed },
        output: { "1": { class_type: "TestNode", inputs: { seed: tab.seed } } },
      };
    },
  };
  const document = {
    querySelectorAll() { return [...tabs.values()]; },
  };
  const posted = [];
  const api = {
    clientId: "test",
    async fetchApi(path, options) {
      if (path.startsWith("/history/")) {
        const id = path.split("/").pop();
        return { ok: true, json: async () => ({
          [id]: { status: { status_str: "success" },
            outputs: config.historyOutputs ?? {} },
        }) };
      }
      if (path === "/workflowdirector/context") {
        return { ok: true, json: async () => ({
          active: true, committed: config.committed ?? {},
        }) };
      }
      if (options?.method === "POST") {
        const request = JSON.parse(options.body);
        posted.push(request);
        if (config.rejectSubmission) {
          throw new Error("Simulated connection loss after POST");
        }
        return { ok: true, json: async () => ({
          run_id: config.badAcknowledgement ? "wrong-run-id" : request.run_id,
          record: { phase: "ready", events: [] },
        }) };
      }
      return { ok: true, json: async () => ({
        run_id: path.split("/").pop(), record: { phase: "completed", events: [] },
      }) };
    },
  };
  const sandbox = {
    document, app, api, console, Date, setTimeout,
    crypto: require("node:crypto"),
  };
  vm.runInNewContext(source, sandbox, { filename: "workflow_director_lab.js" });
  return {
    lab: sandbox.__lab, toasts, tabs, posted, extensions, app, makeTab,
    select(path) { activePath = path; },
    active() { return activePath; },
  };
}

test("a registered tab gets recompiled at run time, including unsaved node changes", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "Klein Q4", "id-A", 101);
  e.makeTab("temp/B", "Klein Q6", "id-B", 202);
  await e.lab.capture("A");
  e.select("temp/B");
  await e.lab.capture("B");
  e.tabs.get("temp/B").seed = 404;
  const result = await e.lab.prepareCurrentSteps([e.lab.state.A, e.lab.state.B]);
  assert.equal(result[0].prompt["1"].inputs.seed, 101);
  assert.equal(result[1].prompt["1"].inputs.seed, 404);
  assert.equal(result[1].name, "Klein Q6");
  assert.equal(e.active(), "temp/B");
  assert.equal(e.lab.state.B.prompt["1"].inputs.seed, 202, "old capture remains immutable");
});

test("missing or renamed tabs fail instead of silently executing old snapshots", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A");
  e.makeTab("temp/B", "B", "id-B");
  await e.lab.capture("A");
  e.select("temp/B");
  await e.lab.capture("B");
  e.tabs.delete("temp/A");
  await assert.rejects(
    () => e.lab.prepareCurrentSteps([e.lab.state.A, e.lab.state.B]),
    /closed or missing/
  );
});

test("workflow identity mismatches fail closed on fresh compile", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A");
  await e.lab.capture("A");
  e.tabs.get("temp/A").id = "replaced-workflow";
  // Prevent spending the entire 12-second UI timeout in the unit test.
  await assert.rejects(
    () => e.lab.prepareCurrentSteps([e.lab.state.A]),
    /Could not verify that ComfyUI loaded the expected canvas/
  );
});

test("step events announce names once and follow the matching workflow tab", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "Klein Q4", "id-A");
  e.makeTab("temp/B", "Klein Q6", "id-B");
  e.lab.state.lastRunId = "run-1";
  e.lab.state.currentSteps = [
    { step_id: "A", name: "Klein Q4", tab_path: "temp/A" },
    { step_id: "B", name: "Klein Q6", tab_path: "temp/B" },
  ];
  const run = {
    record: { events: [
      { kind: "job_state", step_id: "B", job_id: "job-B", detail: "in_progress" },
      { kind: "boundary_completed", step_id: "B", job_id: "job-B" },
    ] },
  };
  e.lab.announceStepEvents(run);
  e.lab.announceStepEvents(run);
  assert.equal(e.active(), "temp/B");
  assert.equal(e.toasts.length, 2);
  assert.match(e.toasts[0].detail, /Klein Q6/);
  assert.match(e.toasts[1].summary, /completed/);
});


test("Run submits the freshly compiled B exactly once, not its stale capture", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A", 11);
  e.makeTab("temp/B", "B", "id-B", 22);
  await e.lab.capture("A");
  e.select("temp/B");
  await e.lab.capture("B");
  e.tabs.get("temp/B").seed = 99;
  await e.lab.startRun([e.lab.state.A, e.lab.state.B]);
  assert.equal(e.posted.length, 1);
  assert.equal(e.posted[0].steps[0].prompt["1"].inputs.seed, 11);
  assert.equal(e.posted[0].steps[1].prompt["1"].inputs.seed, 99);
  assert.equal(e.posted[0].steps[1].tab_path, undefined);
});

test("Run refuses to call the backend when a linked tab was closed", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A");
  e.makeTab("temp/B", "B", "id-B");
  await e.lab.capture("A");
  e.select("temp/B");
  await e.lab.capture("B");
  e.tabs.delete("temp/A");
  await assert.rejects(
    () => e.lab.startRun([e.lab.state.A, e.lab.state.B]),
    /closed or missing/
  );
  assert.equal(e.posted.length, 0);
});



test("ambiguous POST acknowledgement is fail-closed, with known UUID for recovery", async () => {
  const e = makeEnvironment({ rejectSubmission: true });
  e.makeTab("temp/A", "A", "id-A");
  await e.lab.capture("A");
  await assert.rejects(
    () => e.lab.startRun([e.lab.state.A]),
    /Simulated connection loss/
  );
  assert.equal(e.posted.length, 1);
  assert.equal(e.lab.state.monitoringUncertain, true);
  assert.equal(e.lab.state.lastRunId, e.posted[0].run_id);
  await assert.rejects(
    () => e.lab.startRun([e.lab.state.A]),
    /may still be active/
  );
});

test("two workflow tabs sharing the same UUID cannot be linked", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-shared");
  e.makeTab("temp/B", "B", "id-shared");
  await e.lab.capture("A");
  e.select("temp/B");
  await assert.rejects(() => e.lab.capture("B"), /shares a tab or UUID/);
});

test("bad UUID acknowledgement is treated as ambiguous acceptance", async () => {
  const e = makeEnvironment({ badAcknowledgement: true });
  e.makeTab("temp/A", "A", "id-A");
  await e.lab.capture("A");
  await assert.rejects(
    () => e.lab.startRun([e.lab.state.A]),
    /acknowledgement ID mismatch/
  );
  assert.equal(e.lab.state.monitoringUncertain, true);
  assert.equal(e.posted.length, 1);
});

test("Run B only UI action is wired to exactly B and clearly warns about run-scoped Context", () => {
  assert.match(source, /"Run B only",\s*\(\) => startRun\(\[state\.B\]\)/);
  assert.match(source, /Run B only cannot read A from a previous run/);
});

test("Run B only submits one fresh B workflow and never queues A", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A", 31);
  e.makeTab("temp/B", "B", "id-B", 42);
  await e.lab.capture("A");
  e.select("temp/B");
  await e.lab.capture("B");
  e.tabs.get("temp/B").seed = 43;
  await e.lab.startRun([e.lab.state.B]);
  assert.equal(e.posted.length, 1);
  assert.equal(e.posted[0].steps.length, 1);
  assert.equal(e.posted[0].steps[0].step_id, "B");
  assert.equal(e.posted[0].steps[0].workflow_id, "id-B");
  assert.equal(e.posted[0].steps[0].prompt["1"].inputs.seed, 43);
  assert.equal(e.posted[0].steps[0].tab_path, undefined);
});

test("Run B only fails closed when B tab is closed", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A", 31);
  e.makeTab("temp/B", "B", "id-B", 42);
  await e.lab.capture("A");
  e.select("temp/B");
  await e.lab.capture("B");
  e.tabs.delete("temp/B");
  e.select("temp/A");
  await assert.rejects(
    () => e.lab.startRun([e.lab.state.B]),
    /closed or missing/
  );
  assert.equal(e.posted.length, 0);
});


test("GET picker offers keys from captured PUT without waiting for a run", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A");
  await e.lab.capture("A");
  e.lab.state.A.prompt = {
    "1": {
      class_type: "WorkflowDirectorContextPutUniversal",
      inputs: { key: "demo.image" },
    },
    "2": {
      class_type: "WorkflowDirectorContextPutString",
      inputs: { key: "demo.prompt" },
    },
  };
  assert.deepEqual(Array.from(e.lab.plannedContextKeys()),
    ["demo.image", "demo.prompt"]);
  assert.deepEqual(Array.from(e.lab.availableContextKeys()),
    ["demo.image", "demo.prompt"]);

  const widgets = [{ name: "key", value: "shared" }];
  const node = {
    comfyClass: "WorkflowDirectorContextGetUniversal",
    widgets,
    addWidget(kind, name, value, cb, options) {
      const widget = { name, value, callback: cb, options };
      widgets.push(widget);
      return widget;
    },
  };
  const pickerExt = e.extensions.find(
    x => x.name === "WorkflowDirector.ContextKeyPicker");
  pickerExt.nodeCreated(node);
  assert.equal(widgets.length, 2);
  assert.ok(widgets[1].options.values.includes("demo.image"));
  widgets[1].callback("demo.image");
  assert.equal(widgets[0].value, "demo.image",
    "the actual GET key widget is changed");
  assert.equal(widgets[1].serialize, false);
  assert.equal(widgets[1].options.serialize, false,
    "Comfy graphToPrompt must not send UI-only combo as API input");
  pickerExt.nodeCreated(node);
  assert.equal(widgets.length, 2, "never duplicate selector on load");
});

test("Context inspector never supplies a live payload; completed run keys remain labeled snapshots", async () => {
  const e = makeEnvironment();
  e.lab.state.lastRun = { record: {
    context_manifest: { "demo.mystery": { type: "VALUE", bytes: 142 } },
  } };
  assert.ok(e.lab.availableContextKeys().includes("demo.mystery"));
  // A new native Director run must not reuse the old key's value.
  e.lab.state.lastRun = null;
  assert.equal(e.lab.availableContextKeys().includes("demo.mystery"), false);
});

test("completed fast B restores PreviewImage metadata into the correct active canvas", async () => {
  const image = { filename: "preview.png", subfolder: "", type: "temp" };
  const e = makeEnvironment({
    historyOutputs: { "3": { images: [image] } },
  });
  e.makeTab("temp/A", "A", "id-A");
  e.makeTab("temp/B", "B", "id-B");
  e.lab.state.lastRunId = "run-1";
  e.lab.state.currentSteps = [
    { step_id: "A", name: "A", tab_path: "temp/A", workflow_id: "id-A" },
    { step_id: "B", name: "B", tab_path: "temp/B", workflow_id: "id-B" },
  ];
  const run = { run_id: "run-1", record: {
    phase: "completed",
    attempts: [{
      step_id: "B", job_id: "job-B", state: "completed",
    }],
  } };
  await e.lab.synchronizeTerminalOutputs(run);
  assert.equal(e.active(), "temp/B");
  assert.equal(e.app.nodeOutputs["3"].images[0].filename, "preview.png");
  assert.equal(e.lab.state.syncedRunId, "run-1");
});

test("do not apply B image outputs to A when followActive is disabled", async () => {
  const e = makeEnvironment({ historyOutputs: {
    "3": { images: [{ filename: "wrong-graph.png" }] },
  } });
  e.makeTab("temp/A", "A", "id-A");
  e.makeTab("temp/B", "B", "id-B");
  e.lab.state.followActive = false;
  e.lab.state.currentSteps = [
    { step_id: "B", tab_path: "temp/B", workflow_id: "id-B" },
  ];
  await e.lab.synchronizeTerminalOutputs({
    run_id: "run-1",
    record: { phase: "completed", attempts: [
      { step_id: "B", job_id: "job-B", state: "completed" },
    ] },
  });
  assert.equal(e.active(), "temp/A");
  assert.equal(e.app.nodeOutputs?.["3"], undefined);
});


test("three linked tabs run in A → Cleanup → B order with fresh independent prompt snapshots", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "Producer", "id-A", 11);
  e.makeTab("temp/C", "Cleanup", "id-C", 22);
  e.makeTab("temp/B", "Consumer", "id-B", 33);
  await e.lab.capture("A");
  e.select("temp/C");
  await e.lab.capture("C");
  e.select("temp/B");
  await e.lab.capture("B");
  e.tabs.get("temp/C").seed = 222;
  await e.lab.startRun([e.lab.state.A, e.lab.state.C, e.lab.state.B]);
  assert.equal(e.posted.length, 1);
  assert.deepEqual(Array.from(e.posted[0].steps.map((s) => s.step_id)),
    ["A", "C", "B"]);
  assert.equal(e.posted[0].steps[1].prompt["1"].inputs.seed, 222);
  assert.equal(e.posted[0].steps[1].tab_path, undefined);
});

test("Cleanup capture cannot share a tab or workflow UUID with A or B", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A");
  e.makeTab("temp/C", "Cleanup", "id-C");
  await e.lab.capture("A");
  await assert.rejects(() => e.lab.capture("C"), /shares a tab or UUID/);
  e.select("temp/C");
  await e.lab.capture("C");
  e.makeTab("temp/B", "B", "id-C");
  e.select("temp/B");
  await assert.rejects(() => e.lab.capture("B"), /shares a tab or UUID/);
});

test("Cleanup option remains opt-in rather than being inserted in A → B", () => {
  assert.match(source, /"Run A → Cleanup → B"/);
  assert.match(source, /startRun\(\[state\.A, state\.C, state\.B\]\)/);
  assert.match(source, /"Run A → B"/);
  assert.match(source, /startRun\(\[state\.A, state\.B\]\)/);
});


test("missing GET emits a warning toast and preserves original node.onExecuted", () => {
  const e = makeEnvironment();
  const calls = [];
  const widgets = [{ name: "key", value: "render1" }];
  const node = {
    comfyClass: "WorkflowDirectorContextGetUniversal",
    widgets,
    onExecuted(output) { calls.push(output); },
    addWidget(kind, name, value, callback, options) {
      const item = { kind, name, value, callback, options };
      widgets.push(item);
      return item;
    },
  };
  const ext = e.extensions.find(x => x.name === "WorkflowDirector.ContextKeyPicker");
  ext.nodeCreated(node);
  ext.nodeCreated(node); // No wrapper duplication on re-render.
  node.onExecuted({ text: ["WD_CONTEXT_MISSING:render1"] });
  assert.equal(calls.length, 1);
  assert.equal(e.toasts.length, 1);
  assert.equal(e.toasts[0].severity, "warn");
  assert.match(e.toasts[0].detail, /render1/);
  node.onExecuted({ text: ["unrelated node UI output"] });
  assert.equal(calls.length, 2);
  assert.equal(e.toasts.length, 1);
});

test("ordered sequence accepts four independent workflows and compiles fresh at Run", async () => {
  const e = makeEnvironment();
  for (let i = 1; i <= 4; i++) {
    e.makeTab("temp/W" + i, "Workflow " + i, "uuid-" + i, 10 * i);
    e.select("temp/W" + i);
    await e.lab.addSequenceTab("temp/W" + i);
  }
  assert.equal(e.lab.state.sequence.length, 4);
  assert.deepEqual(Array.from(e.lab.state.sequence, s => s.step_id),
    ["W1", "W2", "W3", "W4"]);
  e.tabs.get("temp/W3").seed = 333;
  await e.lab.runSequence();
  assert.equal(e.posted.length, 1);
  assert.equal(e.posted[0].steps.length, 4);
  assert.deepEqual(Array.from(e.posted[0].steps, x => x.step_id),
    ["W1", "W2", "W3", "W4"]);
  assert.equal(e.posted[0].steps[2].prompt["1"].inputs.seed, 333);
  assert.equal(e.posted[0].steps[2].tab_path, undefined);
  assert.equal(e.lab.state.sequence[2].prompt["1"].inputs.seed, 30,
    "captured draft must stay unchanged after fresh compile");
});

test("up/down/remove controls preserve stable IDs and change backend order", async () => {
  const e = makeEnvironment();
  for (const [path, label, id] of [
    ["temp/one", "One", "u1"],
    ["temp/two", "Two", "u2"],
    ["temp/three", "Three", "u3"],
  ]) {
    e.makeTab(path, label, id);
    e.select(path);
    await e.lab.addSequenceTab(path);
  }
  e.lab.moveSequenceStep(2, -1);
  e.lab.removeSequenceStep(0);
  assert.deepEqual(Array.from(e.lab.state.sequence, x => x.step_id),
    ["W3", "W2"]);
  assert.deepEqual(Array.from(e.lab.state.sequence, x => x.workflow_id),
    ["u3", "u2"]);
  e.select("temp/two");
  await e.lab.runSequence();
  assert.deepEqual(Array.from(e.posted[0].steps, x => x.workflow_id),
    ["u3", "u2"]);
  e.select("temp/one");
  await e.lab.addSequenceTab("temp/one");
  assert.equal(e.lab.state.sequence[2].step_id, "W4",
    "step ID is not recycled after removal");
});

test("the same workflow can occur twice in N-step sequence without duplicate job IDs", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/reused", "Reusable", "uuid-same");
  await e.lab.addSequenceTab("temp/reused");
  await e.lab.addSequenceTab("temp/reused");
  await e.lab.runSequence();
  assert.deepEqual(Array.from(e.posted[0].steps, x => x.workflow_id),
    ["uuid-same", "uuid-same"]);
  assert.deepEqual(Array.from(e.posted[0].steps, x => x.step_id),
    ["W1", "W2"]);
});

test("N-workflow capture refuses non-active tab rather than capturing stale canvas", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/one", "One", "uuid-one");
  e.makeTab("temp/two", "Two", "uuid-two");
  await assert.rejects(
    () => e.lab.addSequenceTab("temp/two"),
    /Select the workflow in the ComfyUI top bar/
  );
  assert.equal(e.lab.state.sequence.length, 0);
  assert.equal(e.active(), "temp/one");
});

test("closed or replaced sequence workflow never submits a stale API prompt", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/one", "One", "uuid-one");
  e.makeTab("temp/two", "Two", "uuid-two");
  await e.lab.addSequenceTab("temp/one");
  e.select("temp/two");
  await e.lab.addSequenceTab("temp/two");
  e.tabs.delete("temp/one");
  await assert.rejects(() => e.lab.runSequence(), /closed or missing/);
  assert.equal(e.posted.length, 0);
  e.lab.removeSequenceStep(0);
  e.tabs.get("temp/two").id = "replacement";
  await assert.rejects(
    () => e.lab.runSequence(),
    /Could not verify that ComfyUI loaded the expected canvas/
  );
  assert.equal(e.posted.length, 0);
});

test("N-workflow planned keys appear in universal GET picker", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/producer", "Producer", "uuid-producer");
  await e.lab.addSequenceTab("temp/producer");
  e.lab.state.sequence[0].prompt = {
    "10": {
      class_type: "WorkflowDirectorContextPutUniversal",
      inputs: { key: "render1", value: ["1", 0] },
    },
  };
  assert.ok(e.lab.availableContextKeys().includes("render1"));
});

test("sequence modifications are blocked during a run and monitoring uncertainty", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/one", "One", "uuid-one");
  await e.lab.addSequenceTab("temp/one");
  e.lab.state.isRunning = true;
  assert.throws(() => e.lab.removeSequenceStep(0), /during a run/);
  assert.throws(() => e.lab.moveSequenceStep(0, 1), /during a run/);
  await assert.rejects(
    () => e.lab.addSequenceTab("temp/one"), /Wait for the current run/
  );
  e.lab.state.isRunning = false;
  e.lab.state.monitoringUncertain = true;
  await assert.rejects(
    () => e.lab.runSequence(), /may still be active/
  );
});

test("the full N sequence is temporary in browser state, with no save endpoint", () => {
  assert.match(source, /function renderSequence\(root\)/);
  assert.match(source, /"Run all \("/);
  assert.match(source, /"\+ Add current workflow"/);
  assert.match(source, /sequenceButton\("Remove"/);
  assert.match(source, /sequenceButton\("↑"/);
  assert.match(source, /sequenceButton\("↓"/);
  assert.doesNotMatch(source, /workflowdirector\/sequences\/save/);
});


test("View result restores the selected completed stage, not the final one", async () => {
  const e = makeEnvironment({
    historyOutputs: { "3": { images: [{ filename: "stage-one.png" }] } },
  });
  e.makeTab("temp/one", "Stage 1", "uuid-one");
  e.makeTab("temp/two", "Stage 2", "uuid-two");
  await e.lab.addSequenceTab("temp/one");
  e.select("temp/two");
  await e.lab.addSequenceTab("temp/two");
  const [one, two] = e.lab.state.sequence;
  const runId = "run-123";
  e.lab.state.sequenceRunId = runId;
  e.lab.state.sequenceRunRevision = e.lab.state.sequenceRevision;
  e.lab.state.lastRunId = runId;
  e.lab.state.currentSteps = [one, two];
  e.lab.state.lastRun = {
    run_id: runId,
    record: {
      phase: "completed",
      attempts: [
        { step_id: one.step_id, job_id: "job-one", state: "completed" },
        { step_id: two.step_id, job_id: "job-two", state: "completed" },
      ],
    },
  };
  assert.equal(e.lab.sequenceStepStatus(one), "Completed");
  await e.lab.viewSequenceResult(one);
  assert.equal(e.active(), "temp/one");
  assert.equal(e.app.nodeOutputs["3"].images[0].filename, "stage-one.png");
  e.lab.moveSequenceStep(0, 1);
  await assert.rejects(
    () => e.lab.viewSequenceResult(one),
    /sequence changed since the last run/
  );
});

test("View result rejects noncompleted attempts even when the tab exists", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/one", "Stage 1", "uuid-one");
  await e.lab.addSequenceTab("temp/one");
  const step = e.lab.state.sequence[0];
  e.lab.state.sequenceRunId = "run";
  e.lab.state.sequenceRunRevision = e.lab.state.sequenceRevision;
  e.lab.state.lastRunId = "run";
  e.lab.state.lastRun = { run_id: "run", record: {
    phase: "failed",
    attempts: [{ step_id: step.step_id, job_id: "job", state: "failed" }],
  } };
  e.lab.state.currentSteps = [step];
  await assert.rejects(() => e.lab.viewSequenceResult(step),
    /no completed native job/);
});

test("the N-workflow sequence uses the existing backend without automatically inserting Cleanup", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "A", "id-A");
  e.makeTab("temp/B", "B", "id-B");
  e.select("temp/A"); await e.lab.addSequenceTab("temp/A");
  e.select("temp/B"); await e.lab.addSequenceTab("temp/B");
  await e.lab.runSequence();
  assert.deepEqual(Array.from(e.posted[0].steps, x => x.step_id), ["W1", "W2"]);
  assert.equal(e.posted[0].steps.some(x => x.step_id === "C"), false);
});


test("Run only on an N-sequence row queues that workflow without preceding PUTs", async () => {
  const e = makeEnvironment();
  e.makeTab("temp/A", "Producer", "uuid-producer");
  e.makeTab("temp/B", "Consumer with fallback", "uuid-consumer");
  await e.lab.addSequenceTab("temp/A");
  e.select("temp/B");
  await e.lab.addSequenceTab("temp/B");
  e.tabs.get("temp/B").seed = 23;
  await e.lab.runSequenceStep(e.lab.state.sequence[1]);
  assert.equal(e.posted.length, 1);
  assert.equal(e.posted[0].steps.length, 1);
  assert.equal(e.posted[0].steps[0].workflow_id, "uuid-consumer");
  assert.equal(e.posted[0].steps[0].prompt["1"].inputs.seed, 23);
  assert.equal(e.posted[0].steps[0].step_id, "W2");
});

test("legacy controls retain their open state across frequent panel refreshes", () => {
  assert.match(source, /legacy\.open = state\.legacyExpanded/);
  assert.match(source, /state\.legacyExpanded = legacy\.open/);
  assert.match(source, /"Run only"/);
});


test("GET universal fixes serialized STRING output sockets without dropping IMAGE links", () => {
  const e = makeEnvironment();
  const link = {
    origin_id: 109, origin_slot: 0,
    target_id: 200, target_slot: 0, type: "STRING",
  };
  let configureCalls = 0;
  let connectionsCalls = 0;
  const node = {
    id: 109, type: "WorkflowDirectorContextGetUniversal",
    outputs: [{ name: "value", type: "STRING", links: [77] }],
    graph: { links: { 77: link } },
    widgets: [{ name: "key", value: "render1" }],
    onConfigure() { configureCalls += 1; },
    onConnectionsChange() { connectionsCalls += 1; },
    addWidget(kind, name, value, callback, options) {
      const item = { kind, name, value, callback, options };
      this.widgets.push(item);
      return item;
    },
  };
  const ext = e.extensions.find(x => x.name === "WorkflowDirector.ContextKeyPicker");
  ext.nodeCreated(node);
  assert.equal(node.outputs[0].type, "*",
    "GET must always have a universal socket even after old saved STRING links");
  assert.equal(link.type, "*", "a stale serialized STRING link must not block IMAGE");
  assert.equal(node.outputs[0].name, "value");
  assert.deepEqual(node.outputs[0].links, [77], "never disconnect existing links");

  node.outputs[0].type = "STRING";
  link.type = "STRING";
  node.onConfigure({ outputs: [{ type: "STRING" }] });
  assert.equal(node.outputs[0].type, "*", "rehydrating stale workflow must not stick");
  assert.equal(link.type, "*");
  assert.equal(configureCalls, 1, "original Comfy onConfigure still called");

  node.outputs[0].type = "STRING";
  node.onConnectionsChange(2, 0, true, link);
  assert.equal(node.outputs[0].type, "*", "later connections must not force STRING");
  assert.equal(connectionsCalls, 1, "original connection callback still called");

  ext.nodeCreated(node);
  node.onConnectionsChange(2, 0, true, link);
  assert.equal(connectionsCalls, 2, "never install duplicate wrappers");
  assert.equal(node.widgets.length, 2, "key picker still installed only once");
});

test("GET universal guard does not change PUT MatchType or typed Context Get nodes", () => {
  const e = makeEnvironment();
  const ext = e.extensions.find(x => x.name === "WorkflowDirector.ContextKeyPicker");
  const ordinary = [
    { type: "WorkflowDirectorContextPutUniversal", outputs: [{ type: "COMFY_MATCHTYPE_V3" }] },
    { type: "WorkflowDirectorContextGetString", outputs: [{ type: "STRING" }] },
    { type: "WorkflowDirectorContextGetLatent", outputs: [{ type: "LATENT" }] },
  ];
  for (const node of ordinary) {
    ext.nodeCreated(node);
  }
  assert.deepEqual(ordinary.map(x => x.outputs[0].type),
    ["COMFY_MATCHTYPE_V3", "STRING", "LATENT"]);
});
