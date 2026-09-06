"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const G = require("../../src/pg_diag/render/graph/pg-diag-graph.js");
const definition = require("../../src/pg_diag/render/graph/graph.json");
const fixture = require("../data/diagnostic_graph/lab_snapshots.json");
const Groups = require("../../src/pg_diag/render/graph/pg-diag-graph-groups.js");
function table(rows, columns, status = "ok") {
  return {collection_status: status, result: {kind: "table", columns: (columns || [...new Set(rows.flatMap(Object.keys))]).map(name => ({name})), rows}};
}
function chart(values, extra = {}) {
  return {collection_status: "ok", result: {kind: "chart", series: [{name: "WAL", points: values.map((value, i) => ({t: `2026-09-06T00:00:0${i}Z`, value}))}], ...extra}};
}
function direction(items, parent, name) { return G.evaluate({items}, definition).nodes[parent + ".sources." + name]; }

test("directions preserve parent input assessments and every bound report item", () => {
  const plain = {...definition, nodes: definition.nodes.map(({binding_groups, ...node}) => node)};
  for (const artifact of [fixture, {items: {}}, {items: Object.fromEntries(
    definition.nodes.flatMap(node => node.bindings.map(binding => [binding.id, {
      collection_status: "empty", result: {kind: "table", rows: []}
    }]))
  )}]) {
    const before = G.evaluate(artifact, plain), after = G.evaluate(artifact, definition);
    for (const node of definition.nodes) {
      for (const key of ["ownScore", "reasons", "facts", "evidence", "hints", "error"]) {
        assert.deepEqual(after.nodes[node.id][key], before.nodes[node.id][key], node.id + ": " + key);
      }
      const sourceIds = after.nodes[node.id].children.filter(id => after.nodes[id].kind === "sources");
      const direct = after.nodes[node.id].bindings;
      const grouped = sourceIds.flatMap(id => after.nodes[id].bindings);
      assert.ok(direct.length <= 6, node.id + " card is too long");
      assert.deepEqual(new Set([...direct, ...grouped].map(b => b.id)), new Set(node.bindings.map(b => b.id)));
      for (const id of sourceIds) {
        const group = after.nodes[id];
        assert.ok(group.bindings.length >= 1 && group.bindings.length <= 6, id);
        if (group.score === null) assert.ok(group.hints.length, "an unassessed direction explains why");
        else assert.ok(group.reasons.length, "an assessment includes evidence and criteria");
        if (["warn", "crit"].includes(group.status)) assert.ok(after.nodes[node.id].score >= group.score, "findings reach the parent");
        assert.equal(group.error, null);
        assert.ok(after.order.includes(id), "group is reachable from a root");
      }
    }
    for (const key of ["boundItems", "presentItems"]) {
      assert.deepEqual(after.coverage[key], before.coverage[key], key);
    }
  }
});

test("every direction declares an implemented independent evaluator", () => {
  for (const node of definition.nodes) for (const group of node.binding_groups || []) {
    assert.equal(typeof Groups.evaluators[group.evaluator], "function", node.id + ": " + group.id);
    if (group.evaluator === "reference") assert.ok(group.unassessed_reason);
  }
});

test("connection incident and limit cards retain context charts without scoring their presence", () => {
  const charts = {
    "snapshot_charts_db.activity_sessions_by_state": chart([50, 80, 90]),
    "snapshot_charts_db.database_backends": chart([50, 80, 90])
  };
  const incidents = {"server_log.system_incidents": table([{incident_type: "too_many_connections", occurrences: 582}])};
  for (const parent of ["network.clients.capacity", "health.connections"]) {
    const evaluated = G.evaluate({items: {...charts, ...incidents}}, definition);
    for (const group of ["limits", "sessions", "outcomes"]) {
      const node = evaluated.nodes[parent + ".sources." + group];
      for (const id of Object.keys(charts)) assert.ok(node.bindings.some(binding => binding.id === id && binding.kind === "chart"));
      assert.ok(node.bindings.length <= 6);
    }
    assert.equal(evaluated.nodes[parent + ".sources.outcomes"].status, "crit");
    assert.equal(direction(charts, parent, "outcomes").ownScore, null);
    assert.equal(direction(charts, parent, "limits").ownScore, null);
    const withContext = direction({...charts, ...incidents}, parent, "outcomes");
    const withoutContext = direction(incidents, parent, "outcomes");
    assert.equal(withContext.ownScore, withoutContext.ownScore);
    assert.deepEqual(withContext.facts, withoutContext.facts);
    assert.equal(evaluated.coverage.presentItems, 3, "shared chart links are counted once");
  }
});

test("WAL generation colors use the stated boundaries and carry measured facts", () => {
  const id = "snapshot_charts_db.wal_growth_rate";
  for (const [mib, status] of [[0, "ok"], [1.3, "ok"], [49.9, "ok"], [50, "warn"], [199.9, "warn"], [200, "crit"]]) {
    const node = direction({[id]: chart([mib * 1024 ** 2, mib * 1024 ** 2])}, "disk.write.wal", "activity");
    assert.equal(node.status, status, String(mib));
    assert.match(node.reasons.join(" "), /warning ≥ 50.0 MiB\/s, critical ≥ 200.0 MiB\/s/);
    assert.ok(node.facts["WAL generation p95"]);
    assert.ok(node.evidence.includes(id));
  }
});

test("a WAL LSN, cumulative bytes or an invalid sample cannot establish healthy generation", () => {
  const id = "snapshot_charts_db.wal_growth_rate";
  for (const item of [chart([1]), chart([null, null]), chart([-1, -1]), chart([-1, 1, 1]), {...chart([1, 1]), collection_status: "error"}]) {
    const node = direction({[id]: item, "wal_io_checkpoints.wal_position": table([{current_lsn: "0/ABC"}]),
      "wal_io_checkpoints.wal_statistics": table([{wal_bytes: 1e12}])}, "disk.write.wal", "activity");
    assert.equal(node.status, "no_data");
    assert.ok(node.hints.length);
  }
});

test("measured hidden WAL zeros are healthy, missing samples remain unknown", () => {
  const id = "snapshot_charts_db.wal_growth_rate";
  for (const missing of [0, 1]) {
    const item = chart([], {series: [], sample_count: 2, zero_series: [{name: "WAL", sample_count: 2, missing_count: missing}]});
    item.collection_status = "empty";
    assert.equal(direction({[id]: item}, "disk.write.wal", "activity").status, missing ? "no_data" : "ok");
  }
});

test("WAL generation, statements and durability have independent colors and evidence", () => {
  const items = {
    "snapshot_charts_db.wal_growth_rate": chart([1e6, 1e6]),
    "snapshot_delta_workload.sql_wal_delta": table([{wal_bytes_per_sec: 1e6}]),
    "overview.durability_safety_settings": table([
      {setting_name: "fsync", current_value: "off"}, {setting_name: "full_page_writes", current_value: "on"},
      {setting_name: "synchronous_commit", current_value: "on"}])
  };
  const ev = G.evaluate({items}, definition);
  const base = "disk.write.wal";
  assert.equal(ev.nodes[base + ".sources.activity"].status, "ok");
  assert.equal(ev.nodes[base + ".sources.statements"].status, "ok");
  assert.equal(ev.nodes[base + ".sources.durability"].status, "crit");
  assert.equal(ev.nodes[base].status, "crit");
  assert.equal(ev.nodes.disk.status, "crit");
  assert.ok(ev.nodes[base + ".sources.activity"].reasons.every(r => !r.includes("fsync")));
});

test("connections distinguish current capacity from past refusals and unrelated incidents", () => {
  const base = "network.clients.capacity";
  const items = {"activity_locks.connection_pressure": table([{used_pct: 91}]),
    "server_log.system_incidents": table([{incident_type: "too_many_connections", occurrences: 582}])};
  const ev = G.evaluate({items}, definition);
  assert.equal(ev.nodes[base + ".sources.limits"].status, "warn");
  assert.equal(ev.nodes[base + ".sources.outcomes"].status, "crit");
  assert.equal(ev.nodes[base + ".sources.sessions"].status, "no_data");
  assert.match(ev.nodes[base + ".sources.outcomes"].reasons.join(" "), /582 refused/);
  const other = direction({"server_log.system_incidents": table([{incident_type: "out_of_memory", occurrences: 582}])}, base, "outcomes");
  assert.equal(other.status, "ok");
});

test("unrecognized and explicitly unknown risk levels stay unassessed with their reason", () => {
  for (const level of ["unknown", "unexpected"]) {
    const node = direction({"object_workload.rls_configuration": table([{risk_level: level, risk_reason: "Requires approved security baseline"}])}, "security.object_privileges", "rls");
    assert.equal(node.status, "no_data");
    assert.ok(node.hints.length);
    if (level === "unknown") assert.match(node.hints.join(" "), /Requires approved security baseline/);
  }
});

test("failed retained data and inventory alone do not become healthy directions", () => {
  for (const status of ["error", "unsupported", "skipped"]) {
    const node = direction({"overview.durability_safety_settings": table([{setting_name: "fsync", current_value: "off"}], undefined, status)}, "disk.write.wal", "durability");
    assert.equal(node.score, null);
    assert.ok(node.reasons.every(r => !r.includes("fsync = off")));
  }
  const node = direction({"os.mounts": table([{mount: "/", device: "/dev/nvme0n1"}])}, "disk.saturation", "storage");
  assert.equal(node.status, "no_data");
  assert.match(node.hints.join(" "), /topology/);
});

test("missing durability settings cannot produce OK, but a confirmed unsafe setting stays critical", () => {
  for (const value of ["on", "off"]) {
    const node = direction({"overview.durability_safety_settings": table([{setting_name: "fsync", current_value: value}])}, "disk.write.wal", "durability");
    assert.equal(node.status, value === "on" ? "no_data" : "crit");
    assert.ok(node.hints.length);
  }
});

test("SSD utilization alone remains unknown while measured latency has explicit boundaries", () => {
  const id = "snapshot_charts_os.os_disk_utilization";
  const item = chart([20, 20]); item.result.series[0].name = "util (nvme0n1)";
  const node = direction({[id]: item}, "disk.saturation", "device");
  assert.equal(node.status, "no_data");
  const latency = chart([10, 10]); latency.result.series[0].name = "await (nvme0n1)";
  assert.equal(direction({"snapshot_charts_os.os_disk_latency": latency}, "disk.saturation", "device").status, "crit");
});

test("malformed sender rows are not interpreted as replication failures", () => {
  const node = direction({"replication.physical_replication": table([{application_name: "replica"}])}, "health.replication", "senders");
  assert.equal(node.status, "no_data");
  assert.match(node.hints.join(" "), /valid lag measurement/);
});

test("source groups keep empty and failed report items reachable and expose unbound items", () => {
  const node = definition.nodes.find(node => node.id === "health.replication");
  for (const status of ["ok", "empty", "skipped", "unsupported", "error"]) {
    const items = Object.fromEntries(node.bindings.map(b => [b.id, {
      title: b.id, collection_status: status, result: {kind: "table", columns: [{name: "value"}], rows: [[1]]}
    }]));
    items["custom.extra"] = {collection_status: "empty", result: {kind: "table", rows: []}};
    const ev = G.evaluate({items}, definition);
    assert.deepEqual(ev.coverage.unboundItems, ["custom.extra"]);
    const groups = ev.nodes[node.id].children.map(id => ev.nodes[id]);
    assert.equal(groups.flatMap(group => group.bindings).length, node.bindings.length);
    for (const group of groups) {
      assert.ok(group.bindings.every(binding => binding.presence !== "absent"));
      if (["skipped", "unsupported", "error"].includes(status)) assert.equal(group.score, null);
    }
  }
});

test("incomplete log windows cannot prove absence of incidents in parents or directions", () => {
  const items = {
    "server_log.system_incidents": table([], ["incident_type", "occurrences"]),
    "server_log.authentication_failures": table([], ["occurrences"]),
    "server_log.deadlock_events": table([], ["occurrences"]),
    "server_log.replication_events": table([], ["event_type", "severity"]),
    "server_log.error_chronology": table([], ["sql_state", "occurrences"])
  };
  const affected = ["health.crashes", "network.clients.disconnects", "network.replication.failures", "security.authentication",
    "health.crashes.sources.events", "health.connections.sources.outcomes", "disk.space.sources.incidents",
    "health.locks.sources.deadlocks", "health.replication.sources.events", "security.authentication.sources.events"];
  for (const coverage of [{window_truncated: true}, {ranking_complete: false}, {files_unreadable: 1}, {locale_supported: false}]) {
    const ev = G.evaluate({items, runtime: {log_collection: {status: "collected", coverage}}}, definition);
    for (const id of affected) {
      assert.equal(ev.nodes[id].ownStatus, "no_data", id);
      assert.match(ev.nodes[id].hints.join(" "), /log window is incomplete/, id);
    }
    const positive = structuredClone(items);
    positive["server_log.system_incidents"] = table([{incident_type: "too_many_connections", occurrences: 582}]);
    const found = G.evaluate({items: positive, runtime: {log_collection: {status: "collected", coverage}}}, definition);
    assert.equal(found.nodes["health.connections.sources.outcomes"].status, "crit");
    assert.match(found.nodes["health.connections.sources.outcomes"].reasons.join(" "), /582 refused/);
  }
  const complete = G.evaluate({items, runtime: {log_collection: {status: "collected", coverage: {window_truncated: false, ranking_complete: true}}}}, definition);
  assert.equal(complete.nodes["health.crashes.sources.events"].status, "ok");
  assert.equal(complete.nodes["security.authentication.sources.events"].status, "ok");
});

test("row caps and collector degradation cannot turn a partial risk check green", () => {
  for (const modify of [
    item => { item.result.omitted_series_count = 1; },
    item => { item.result.rows[0].candidate_sample_truncated = true; },
    item => { item.diagnostics = [{level: "warning", message: "Sample incomplete"}]; }
  ]) {
    for (const [risk_level, expected] of [["ok", "no_data"], ["high", "crit"]]) {
      const item = table([{risk_level}]); modify(item);
      // Include the added field in the real column schema as well.
      item.result.columns = Object.keys(item.result.rows[0]).map(name => ({name}));
      const ev = G.evaluate({items: {"object_workload.rls_configuration": item}}, definition);
      assert.equal(ev.nodes["security.object_privileges"].ownStatus, expected);
      assert.equal(ev.nodes["security.object_privileges.sources.rls"].status, expected);
    }
  }
});

test("unknown risk and inventory never certify parent health", () => {
  for (const risk_level of ["unknown", "unrecognized", null]) {
    const ev = G.evaluate({items: {"object_workload.rls_configuration": table([{risk_level, risk_reason: "Needs approved baseline"}])}}, definition);
    assert.equal(ev.nodes["security.object_privileges"].status, "no_data");
    assert.match(ev.nodes["security.object_privileges"].hints.join(" "), /approved baseline/);
  }
  const ev = G.evaluate({items: {"overview.server_version": table([{version: "PostgreSQL 18"}])}}, definition);
  for (const id of ev.roots) assert.equal(ev.nodes[id].status, "no_data", id);
  assert.equal(ev.nodes["health.platform"].status, "no_data");
  assert.match(ev.nodes["health.platform"].hints.join(" "), /inventory/);
});

test("parent and direction use identical warning and critical connection boundaries", () => {
  for (const [used_pct, expected] of [[79.99, "ok"], [80, "warn"], [91, "warn"], [94.99, "warn"], [95, "crit"]]) {
    const ev = G.evaluate({items: {"activity_locks.connection_pressure": table([{used_pct}])}}, definition);
    for (const id of ["health.connections", "network.clients.capacity"]) {
      assert.equal(ev.nodes[id].ownStatus, expected, id + ": " + used_pct);
      assert.equal(ev.nodes[id + ".sources.limits"].status, expected);
    }
  }
});

test("standby restartpoints contribute to the checkpoint sync-time denominator", () => {
  for (const [checkpoints, restartpoints, sync, expected] of [[0, 3, 309, "ok"], [1, 1, 3000, "ok"], [0, 3, 6000, "warn"], [0, 3, 30000, "crit"], [null, 3, 309, "no_data"], [0, null, 0, "no_data"]]) {
    const items = {"snapshot_delta_workload.checkpointer_delta": table([{
      checkpoints_done_delta: checkpoints, restartpoints_done_delta: restartpoints, sync_time_ms_delta: sync
    }])};
    for (const parent of ["disk.write.checkpoints", "cpu.iowait.write.data.checkpoints"]) {
      const node = direction(items, parent, "timing");
      assert.equal(node.status, expected);
      if (expected !== "no_data") assert.match(node.reasons.join(" "), /per completed checkpoint\/restartpoint/);
    }
  }
});

test("logical errors and conflicts are separate overlapping counters and empty deltas are not zero", () => {
  const delta = "snapshot_delta_workload.subscription_errors_conflicts_delta";
  let node = direction({[delta]: table([{subname: "sub", apply_error_count_delta: 2, sync_error_count_delta: 0, conflict_count_delta: 2}])}, "health.replication", "logical");
  assert.equal(node.status, "warn");
  assert.equal(node.facts["Apply errors in window"], "2");
  assert.equal(node.facts["Logical conflicts in window"], "2");
  assert.match(node.reasons.join(" "), /overlap and are not added/);
  assert.equal(direction({[delta]: table([], ["apply_error_count_delta"])}, "health.replication", "logical").status, "no_data");
  node = direction({[delta]: table([], ["apply_error_count_delta"]), "replication.subscription_workers": table([
    {subname: "sub", subenabled: true, worker_running: true, apply_error_count: 2, sync_error_count: 0}
  ])}, "health.replication", "logical");
  assert.equal(node.status, "warn", "running workers do not erase collected historical failures");
  assert.equal(node.facts["Apply errors since statistics reset"], "2");
});

test("logical table synchronization findings are assessed even with a running apply worker", () => {
  const ev = G.evaluate({items: {
    "replication.subscription_workers": table([{subname: "sub", subenabled: true, worker_running: true}]),
    "replication.subscription_table_sync": table([{subscription_name: "sub", risk_level: "medium", risk_reason: "Initial synchronization is stalled"}])
  }}, definition);
  for (const id of ["health.replication.sources.logical", "network.replication.streams.sources.streams"]) {
    assert.equal(ev.nodes[id].status, "warn");
    assert.match(ev.nodes[id].reasons.join(" "), /synchronization is stalled/);
  }
});

test("recovery conflicts use cumulative counters only with an explicit historical explanation", () => {
  const id = "replication.standby_conflicts";
  for (const [conflicts_total, status] of [[0, "ok"], [5, "warn"], [null, "no_data"]]) {
    const node = direction({[id]: table([{datname: "db", conflicts_total}])}, "health.replication", "recovery");
    assert.equal(node.status, status);
    assert.match(node.reasons.join(" "), /history since statistics reset/);
  }
});

test("temporary file rate can use a valid database delta without a chart", () => {
  const item = table([{datname: "a", temp_bytes_per_sec: 3 * 1024 ** 2}, {datname: "b", temp_bytes_per_sec: 3 * 1024 ** 2}]);
  const node = direction({"snapshot_delta_workload.database_workload_delta": item}, "disk.write.temp_files", "database");
  assert.equal(node.status, "warn");
  assert.match(node.reasons.join(" "), /6.0 MiB\/s/);
});

test("receiver absence needs recovery-role context, and malformed senders are unknown", () => {
  for (const recovery of [true, false, undefined]) {
    const ev = G.evaluate({runtime: {in_recovery: recovery}, items: {"replication.wal_receiver": table([], ["status"])}}, definition);
    assert.equal(ev.nodes["network.replication.receive"].ownStatus, recovery === false ? "ok" : "no_data");
  }
  const ev = G.evaluate({items: {"replication.physical_replication": table([{application_name: "replica"}])}}, definition);
  assert.equal(ev.nodes["health.replication"].ownStatus, "no_data");
});

test("informational replication logs do not become warnings in the parent", () => {
  const ev = G.evaluate({items: {"server_log.replication_events": table([{event_type: "streaming", severity: "LOG", occurrences: 100}])}}, definition);
  assert.equal(ev.nodes["health.replication"].ownStatus, "ok");
  assert.equal(ev.nodes["health.replication.sources.events"].status, "ok");
});

test("a healthy checkpoint sub-check cannot certify CPU without CPU measurements", () => {
  const ev = G.evaluate({items: {
    "server_log.checkpoints": table([{sync_seconds_max: 0.2, event_type: "checkpoint"}]),
    "snapshot_delta_workload.checkpointer_delta": table([{checkpoints_done_delta: 1, restartpoints_done_delta: 0, sync_time_ms_delta: 200}])
  }}, definition);
  assert.equal(ev.nodes["cpu.iowait.write.data.checkpoints.sources.timing"].status, "ok");
  assert.equal(ev.nodes["cpu.iowait"].status, "no_data");
  assert.equal(ev.nodes.cpu.status, "no_data");
});

test("an unused degraded context item does not invalidate measured sender lag", () => {
  const cpu = table([{cpu_pct: 0}]);
  cpu.diagnostics = [{level: "warning", message: "Short-lived processes were omitted"}];
  const ev = G.evaluate({items: {
    "backend_os.backend_proc_cpu": cpu,
    "replication.physical_replication": table([{application_name: "standby", current_to_sent_lag_bytes: 0, sent_to_write_lag_bytes: 0}])
  }}, definition);
  assert.equal(ev.nodes["network.replication.send"].ownStatus, "ok");
  assert.equal(ev.nodes["network.replication.send.sources.senders"].status, "ok");
});

test("replication capacity checks are role-aware and retain explicit exhausted-resource findings", () => {
  const id = "replication.replication_capacity";
  const item = table([{resource: "replication_slots", utilization_pct: 0, risk_level: "ok"},
    {resource: "wal_level", setting_value: "replica", utilization_pct: null, risk_level: "medium", risk_reason: "Publications exist but wal_level is not logical"}]);
  for (const in_recovery of [true, false]) {
    const ev = G.evaluate({runtime: {in_recovery}, items: {[id]: item}}, definition);
    for (const nodeId of ["health.replication.sources.slots", "network.replication.streams.sources.capacity"]) {
      assert.equal(ev.nodes[nodeId].status, in_recovery ? "no_data" : "warn");
      if (in_recovery) assert.match(ev.nodes[nodeId].hints.join(" "), /upstream primary/);
    }
  }
  const full = table([{resource: "logical_replication_workers", utilization_pct: null, risk_level: "high", risk_reason: "Enabled subscriptions have no worker capacity"}]);
  assert.equal(direction({[id]: full}, "network.replication.streams", "capacity").status, "crit");
});
