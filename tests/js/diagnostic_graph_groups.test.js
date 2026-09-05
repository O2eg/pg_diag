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
