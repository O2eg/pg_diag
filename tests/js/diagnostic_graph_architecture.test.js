"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const G = require("../../src/pg_diag/render/graph/pg-diag-graph.js");
const Data = require("../../src/pg_diag/render/graph/pg-diag-graph-data.js");
const definition = require("../../src/pg_diag/render/graph/graph.json");
const fixture = require("../data/diagnostic_graph/lab_snapshots.json");
const copy = value => JSON.parse(JSON.stringify(value));
const itemIds = [...new Set(definition.nodes.flatMap(node => node.bindings.map(binding => binding.id)))];
function table(rows, status = "ok") {
  return {collection_status: status, result: {kind: "table", columns: [...new Set(rows.flatMap(Object.keys))].map(name => ({name, encoding: "json_value"})), rows}};
}
function chart(values, extra = {}) {
  return {collection_status: "ok", result: {kind: "chart", series: [{name: "user", points: values.map((value, n) => ({t: `2026-09-05T00:00:0${n}Z`, value}))}], ...extra}};
}
function assertNoErrors(evaluation) {
  for (const node of Object.values(evaluation.nodes)) assert.equal(node.error, null, node.id + ": " + node.error);
}
function ownEvidence(node) {
  return {score: node.ownScore, facts: node.facts, reasons: node.reasons};
}

// Audit actual reads, including fallback lookups and resource-pressure helpers.
function checkBindings(artifact, graph = definition) {
  const nodes = Object.fromEntries(graph.nodes.map(node => [node.id, node]));
  const allowed = {};
  for (const node of graph.nodes) {
    const ids = allowed[node.id] = new Set();
    for (let current = node; current; current = nodes[current.parent]) {
      for (const binding of current.bindings) ids.add(binding.id);
    }
  }
  const seen = new Set();
  const result = G.evaluate(artifact, graph, {onRead(node, item, method) {
    seen.add(node);
    assert.ok(allowed[node].has(item), `${node}: undeclared ${method}(${item})`);
  }});
  assertNoErrors(result);
  return seen;
}

test("every rule has a declared implementation and explicit valid parameters", () => {
  for (const node of definition.nodes) {
    assert.equal(typeof G.evaluators[node.evaluator || "generic"], "function", node.id);
    if (node.evaluator === "network_throughput") {
      assert.ok(["snapshot_charts_os.os_network_receive", "snapshot_charts_os.os_network_transmit"].includes(node.params.metric));
      assert.ok(node.bindings.some(binding => binding.id === node.params.metric));
    }
    if (node.evaluator === "network_interface_events") assert.ok(["errors", "drops"].includes(node.params.event));
    if (node.evaluator === "network_settings") assert.ok(["tcp", "udp"].includes(node.params.protocol));
    if (node.evaluator === "network_client_waits") assert.ok(["ClientRead", "ClientWrite"].includes(node.params.waitEvent));
  }
});

test("actual rule reads belong to own or ancestor bindings, including empty-source fallbacks", () => {
  const seen = new Set();
  const dir = path.join(__dirname, "../data/diagnostic_graph");
  for (const file of fs.readdirSync(dir).filter(file => file.endsWith(".json"))) {
    const artifact = JSON.parse(fs.readFileSync(path.join(dir, file)));
    if (artifact.items) for (const node of checkBindings(artifact)) seen.add(node);
  }
  const empty = {items: Object.fromEntries(itemIds.map(id => [id, table([], "empty")])), runtime: {mode: "snapshots", collection_mode: "local"}};
  for (const node of checkBindings(empty)) seen.add(node);
  for (const node of definition.nodes.filter(node => node.evaluator !== "aggregate")) assert.ok(seen.has(node.id), node.id);
  const incomplete = copy(definition);
  incomplete.nodes.find(node => node.id === "network.clients.capacity").bindings = incomplete.nodes.find(node => node.id === "network.clients.capacity").bindings.filter(binding => binding.id !== "snapshot_delta_workload.database_session_outcomes_delta");
  assert.throws(() => checkBindings(empty, incomplete), /undeclared/, "the guard catches a removed dependency");
});

test("retained payloads of failed sources cannot affect any rule's evidence", () => {
  const graph = copy(definition);
  for (const node of graph.nodes) node.bindings.push({id: "test.collected", role: "support"});
  for (const status of ["error", "skipped", "unsupported", "unknown"]) {
    const retained = copy(fixture);
    const absentPayload = copy(fixture);
    for (const id of Object.keys(retained.items)) {
      retained.items[id].collection_status = status;
      absentPayload.items[id].collection_status = status;
      delete absentPayload.items[id].result;
    }
    // A separate collected source opens the evaluation gate in both artifacts.
    retained.items["test.collected"] = absentPayload.items["test.collected"] = table([], "empty");
    const a = G.evaluate(retained, graph), b = G.evaluate(absentPayload, graph);
    assertNoErrors(a); assertNoErrors(b);
    for (const node of graph.nodes) assert.deepEqual(ownEvidence(a.nodes[node.id]), ownEvidence(b.nodes[node.id]), status + " " + node.id);
  }
});

test("failed connection-pressure payload cannot produce a critical health verdict", () => {
  const result = G.evaluate({items: {
    "activity_locks.connection_pressure": table([{used_pct: 100, used_connections: 100, max_connections: 100}], "error"),
    "server_log.system_incidents": table([], "empty")
  }}, definition);
  assert.equal(result.nodes["health.connections"].score, null);
  assert.ok(result.nodes["health.connections"].reasons.every(reason => !reason.includes("100 connections")));
});

test("session failures alone provide scored connection-capacity evidence", () => {
  const source = "snapshot_delta_workload.database_session_outcomes_delta";
  const result = G.evaluate({items: {
    [source]: table([{sessions_fatal_delta: 50, sessions_killed_delta: 0, sessions_abandoned_delta: 0}])
  }}, definition);
  const node = result.nodes["network.clients.capacity"];
  assert.equal(node.error, null);
  assert.equal(node.ownScore, 0.6);
  assert.ok(node.evidence.includes(source));
});

test("the shared accessor retains events and complete hidden zeros but rejects short rate series", () => {
  const rate = chart([99]);
  const event = chart([1], {chart: {tooltip_kind: "log_event"}});
  const zero = chart([], {series: [], sample_count: 2, zero_series: [{name: "user", sample_count: 2, missing_count: 0}]});
  zero.collection_status = "empty";
  const access = Data.createAccess({rate, event, zero, stale: table([{value: 1}], "empty")});
  assert.equal(access.presence("rate"), "empty");
  assert.deepEqual(access.series("rate"), []);
  assert.equal(access.series("event").length, 1);
  assert.deepEqual(access.rows("stale"), []);
  assert.equal(Data.observedZeros(access, "zero").length, 1);
  zero.diagnostics = [{level: "warning", message: "Sampler failed"}];
  assert.deepEqual(Data.observedZeros(access, "zero"), []);
});

test("one valid event-counter interval is evidence in current and older chart formats", () => {
  for (const metadata of [
    {chart: {unit: "deadlocks"}},
    {chart: {unit: "count", quantity: "deadlocks"}},
    {chart: {unit: "count"}, series: {unit: "count", semantic_role: "counter_delta"}},
    {chart: {unit: "count"}, series: {unit: "count", quantity: "events"}}
  ]) {
    const item = chart([null, 100], {chart: metadata.chart});
    Object.assign(item.result.series[0], metadata.series);
    const access = Data.createAccess({events: item});
    assert.equal(access.presence("events"), "present");
    assert.equal(access.minimumSamples("events"), 1);
    assert.equal(access.series("events").length, 1);
  }
  // A count-valued gauge is still a sampled time series, not an event counter.
  const gauge = chart([100], {chart: {unit: "count", quantity: "sessions"}});
  assert.deepEqual(Data.createAccess({gauge}).series("gauge"), []);
});

test("a writer-pressure event interval remains visible without a second interval", () => {
  const events = chart([null, 100], {chart: {unit: "count"}});
  events.result.series[0].quantity = "events";
  const disk = chart([100, 100]);
  disk.result.series[0].name = "await (sda)";
  const result = G.evaluate({items: {
    "snapshot_charts_db.writer_pressure_events": events,
    "snapshot_charts_os.os_disk_latency": disk
  }}, definition);
  assert.equal(result.nodes["disk.write.backend_writes"].ownStatus, "warn");
  assert.ok(result.nodes["disk.write.backend_writes"].reasons.some(reason => reason.includes("100 writer pressure events")));
});

test("sparse wait profiles use observed counts and preserve the absolute LWLock signal", () => {
  const profile = chart([30, 30]);
  profile.result.series[0].name = "LWLock.BufferContent.1";
  profile.result.series.push({name: "Not waiting.Active.2", points: [
    {t: "2026-09-05T00:00:02Z", value: 1},
    {t: "2026-09-05T00:00:03Z", value: 1}
  ]});
  const cpu = chart([50, 50]);
  cpu.result.series[0].name = "system";
  const items = {
    "activity_locks.wait_events": table([{wait_event_type: "Not waiting", sessions: 1}]),
    "activity_locks.wait_event_sample_profile": profile,
    "snapshot_charts_os.os_cpu_utilization": cpu
  };
  const node = G.evaluate({items}, definition).nodes["cpu.contention"];
  assert.equal(node.ownScore, 1);
  assert.ok(node.reasons.some(reason => reason.includes("p95 30.0 sessions")));

  // Use sums over the observed window: means of different-length series
  // would incorrectly report 40% instead of the observed 20% (10 / 50).
  profile.result.series[0].points.forEach(point => { point.value = 5; });
  profile.result.series[1].points.forEach(point => { point.value = 10; });
  profile.result.series[1].points.push(
    {t: "2026-09-05T00:00:00Z", value: 10},
    {t: "2026-09-05T00:00:01Z", value: 10}
  );
  const changed = G.evaluate({items: copy(items)}, definition).nodes["cpu.contention"];
  assert.equal(changed.ownScore, 0);
  assert.ok(changed.reasons.some(reason => reason.includes("20 % of observed top-N")));
});

test("timestamp alignment has explicit strict and observed missing-value policies", () => {
  const a = {times: ["2026-09-05T00:00:00Z", "2026-09-05T00:00:01Z"], values: [10, 20]};
  const b = {times: ["2026-09-05T03:00:01+03:00", "2026-09-05T00:00:02Z"], values: [30, 40]};
  assert.deepEqual(Data.sumSeries([a, b], {missing: "strict"}), [NaN, 50, NaN]);
  assert.deepEqual(Data.sumSeries([a, b], {missing: "observed"}), [10, 50, 40]);
  assert.equal(Data.seriesStats(Data.sumSeries([a, b], {missing: "strict"}), 2), null);
  const duplicates = {times: [a.times[0], a.times[0]], values: [1, 2]};
  assert.deepEqual(Data.sumSeries([a, duplicates], {missing: "strict"}), [NaN, NaN]);
});

test("mixed series with only one matching valid component sample remain unknown", () => {
  const cpu = chart([40, 40, null]);
  cpu.result.series.push({name: "nice", points: [null, 60, 60].map((value, n) => ({t: `2026-09-05T00:00:0${n}Z`, value}))});
  const result = G.evaluate({items: {"snapshot_charts_os.os_cpu_utilization": cpu}}, definition);
  assert.equal(result.nodes["cpu.utilization"].ownScore, null);
});

test("source duration and server wall-clock log windows are browser-timezone independent", () => {
  const runtime = {duration_seconds: 30, snapshot_window_started_at: "2026-09-05T00:00:00Z", snapshot_window_finished_at: "2026-09-05T00:01:00Z",
    log_collection: {coverage: {covered_from: "2026-03-08 01:30:00", covered_to: "2026-03-08 03:30:00"}}};
  const previous = process.env.TZ;
  try {
    for (const zone of ["UTC", "Europe/Moscow", "America/New_York"]) {
      process.env.TZ = zone;
      assert.equal(Data.windowSeconds(runtime, {result: {delta_window: {duration_seconds: 120}}}), 120);
      assert.equal(Data.windowSeconds(runtime, {result: {delta_window: {duration_seconds: 0}}}), null);
      assert.equal(Data.windowSeconds(runtime), 60);
      assert.equal(Data.logWindowMinutes(runtime), 120);
    }
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test("pressure runs once, then cap applies, then children propagate", () => {
  const bindings = [{id: "snapshot_charts_os.os_cpu_utilization", role: "primary"}];
  const root = {id: "r", evaluator: "probe", pressure: "cpu_user", bindings};
  const artifact = {items: {"snapshot_charts_os.os_cpu_utilization": chart([0, 0])}};
  const options = {evaluators: {probe: () => 1}};
  const evaluate = nodes => G.evaluate(artifact, {roots: ["r"], nodes, links: []}, options).nodes.r;
  assert.equal(evaluate([root]).ownScore, 0.2);
  assert.equal(evaluate([{...root, cap: 0.1}]).ownScore, 0.1);
  const propagated = evaluate([{...root, cap: 0.1}, {id: "c", parent: "r", evaluator: "probe", bindings}]);
  assert.equal(propagated.ownScore, 0.1);
  assert.equal(propagated.score, 1);
});

test("renaming nodes and reversing traversal preserve scores and explanations", () => {
  const graph = copy(definition);
  const names = Object.fromEntries(graph.nodes.map((node, n) => [node.id, "renamed_" + n]));
  for (const node of graph.nodes) {
    node.id = names[node.id];
    if (node.parent) node.parent = names[node.parent];
  }
  graph.roots = graph.roots.map(id => names[id]).reverse();
  graph.nodes.reverse();
  graph.links = graph.links.map(link => ({...link, from: names[link.from], to: names[link.to]}));
  const artifact = copy(fixture);
  // Ensure all parameterized network rules execute, even on this older fixture.
  for (const node of definition.nodes.filter(node => node.params)) for (const binding of node.bindings) artifact.items[binding.id] ||= table([], "empty");
  const a = G.evaluate(artifact, definition), b = G.evaluate(artifact, graph);
  assertNoErrors(a); assertNoErrors(b);
  for (const [id, node] of Object.entries(a.nodes)) assert.deepEqual(ownEvidence(node), ownEvidence(b.nodes[names[id]]), id);
});

test("browser UMD assets and CommonJS expose the same public evaluation", () => {
  const context = vm.createContext({});
  for (const file of ["pg-diag-graph-data.js", "pg-diag-graph-rules.js", "pg-diag-graph.js"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../../src/pg_diag/render/graph", file), "utf8"), context);
  }
  assert.deepEqual(copy(context.PgDiagGraph.evaluate(fixture, definition)), G.evaluate(fixture, definition));
});

test("invalid explicit parameters fail visibly instead of choosing a different metric", () => {
  for (const node of definition.nodes.filter(node => node.params)) {
    const invalid = {...node, parent: undefined, params: {}};
    const artifact = {items: Object.fromEntries(node.bindings.map(binding => [binding.id, table([], "empty")]))};
    const result = G.evaluate(artifact, {roots: [node.id], nodes: [invalid], links: []});
    assert.match(result.nodes[node.id].error, /Invalid or missing/, node.id);
    assert.equal(result.nodes[node.id].ownScore, null);
  }
  assert.throws(() => Data.sumSeries([], {missing: "typo"}), /Unknown missing-value policy/);
});
