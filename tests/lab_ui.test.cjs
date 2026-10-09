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
  "availableContextKeys, plannedContextKeys, attachGetKeySelector, synchronizeTerminalOutputs };";

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
  await assert.rejects(() => e.lab.capture("B"), /same workflow UUID/);
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
  assert.match(source, /Context from a previous Director run/);
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
  assert.equal(e.app.nodeOutputs["3"], undefined);
});
