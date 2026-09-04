"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..", "..");
const GRAPH_DIR = path.join(ROOT, "src", "pg_diag", "render", "graph");
const FIXTURES = path.join(ROOT, "tests", "data", "diagnostic_graph");
const G = require(path.join(GRAPH_DIR, "pg-diag-graph.js"));
const definition = JSON.parse(fs.readFileSync(path.join(GRAPH_DIR, "graph.json"), "utf8"));

function fixture(name) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));
}

function table(itemId, columns, rows, status) {
  return {
    item_id: itemId,
    section_id: itemId.split(".")[0],
    title: itemId,
    collection_status: status || (rows.length ? "ok" : "empty"),
    result: {kind: "table", columns: columns.map((c) => (typeof c === "string" ? {name: c, encoding: "json_number"} : c)), rows, row_count: rows.length}
  };
}

function chart(itemId, series) {
  return {
    item_id: itemId,
    section_id: itemId.split(".")[0],
    title: itemId,
    collection_status: "ok",
    result: {
      kind: "chart",
      chart: {kind: "line", unit: "count"},
      series: series.map(([name, values]) => ({name, unit: "count", points: values.map((value, index) => ({t: "2026-09-04T00:00:0" + index + "Z", value}))}))
    }
  };
}

function artifact(items, runtime) {
  const map = {};
  for (const item of items) map[item.item_id] = item;
  return {items: map, runtime: Object.assign({mode: "snapshots", collection_mode: "local", duration_seconds: 240}, runtime || {})};
}

test("scale and statusOf follow the thresholds contract", () => {
  assert.equal(G.scale(50, 70, 95), 0);
  assert.equal(G.scale(95, 70, 95), 1);
  assert.ok(Math.abs(G.scale(82.5, 70, 95) - 0.5) < 1e-9);
  assert.equal(G.scale(5, 10, 3), 0.7142857142857143); // reversed thresholds: lower is worse
  assert.equal(G.statusOf(null), "no_data");
  assert.equal(G.statusOf(0.1), "ok");
  assert.equal(G.statusOf(0.5), "warn");
  assert.equal(G.statusOf(0.9), "crit");
});

test("decodeCell and tableRows decode decimal strings, numbers and booleans", () => {
  const item = table("x.y", [{name: "n", encoding: "decimal_string"}, {name: "f", encoding: "json_number"}, {name: "b", encoding: "json_boolean"}, {name: "s", encoding: "json_string"}], [["123456789012", 1.5, true, "text"], [null, null, null, null]]);
  const rows = G.tableRows(item);
  assert.deepEqual(rows[0], {n: 123456789012, f: 1.5, b: true, s: "text"});
  assert.deepEqual(rows[1], {n: null, f: null, b: null, s: null});
  assert.equal(G.itemPresence(item), "present");
  assert.equal(G.itemPresence(table("x.z", ["a"], [])), "empty");
  assert.equal(G.itemPresence({collection_status: "skipped"}), "skipped");
  assert.equal(G.itemPresence(undefined), "absent");
});

test("chartSeries statistics skip non-finite points", () => {
  const item = chart("c.x", [["a", [1, null, 3, 5]]]);
  const series = G.chartSeries(item);
  assert.equal(series[0].finite, 3);
  const stats = G.seriesStats(series[0].values);
  assert.equal(stats.n, 3);
  assert.equal(stats.max, 5);
  assert.equal(stats.last, 5);
  assert.equal(stats.mean, 3);
  assert.deepEqual(G.sumSeries([{values: [1, 2]}, {values: [NaN, 3, 4]}]), [1, 5, 4]);
});

test("classifyProcess recognizes PostgreSQL process titles", () => {
  assert.equal(G.classifyProcess("postgres: checkpointer"), "checkpointer");
  assert.equal(G.classifyProcess("postgres: autovacuum worker db1"), "autovacuum");
  assert.equal(G.classifyProcess("postgres: walsender rep 10.0.0.1(1234) streaming 0/1"), "walsender");
  assert.equal(G.classifyProcess("postgres: app app_db 127.0.0.1(5) idle"), "client");
  assert.equal(G.classifyProcess("postgres -D /var/lib/postgresql"), "postmaster");
  assert.equal(G.classifyProcess("bash"), "other");
});

test("facts read cores, memory, media, build flags and process tree from item shapes", () => {
  const art = artifact([
    {item_id: "os.cpu_info", section_id: "os", collection_status: "ok", result: {kind: "plain_text", data: "Architecture: x86_64\nCPU(s):  16\nModel name: Demo CPU 3.2GHz\n"}},
    table("os.memory_info", [{name: "metric", encoding: "json_string"}, {name: "value_normalized", encoding: "decimal_string"}], [["MemTotal", "68719476736"], ["MemAvailable", "34359738368"], ["SwapTotal", "0"], ["SwapFree", "0"]]),
    table("os.lshw_disk", [{name: "logicalname", encoding: "json_string"}, {name: "description", encoding: "json_string"}], [["/dev/nvme0n1", "NVMe disk"], ["/dev/sda", "ATA Disk"]]),
    table("overview.pg_config", [{name: "parameter", encoding: "json_string"}, {name: "value", encoding: "json_string"}], [["CONFIGURE", "--enable-cassert --enable-debug"], ["CFLAGS", "-O2"]]),
    {item_id: "backend_os.postgres_process_tree", section_id: "backend_os", collection_status: "ok", result: {kind: "plain_text", data: "  PID PPID USER STAT ELAPSED %CPU %MEM COMMAND COMMAND\n   10    1 postgres Ss 00:10  0.0 0.1 postgres postgres: checkpointer\n   11    1 postgres Ss 00:10  1.5 0.2 postgres postgres: app db 127.0.0.1(1) idle\n   12    1 postgres Ss 00:10  9.0 0.2 postgres postgres: autovacuum worker db\n"}}
  ]);
  const ev = G.evaluate(art, definition);
  const build = ev.nodes["cpu.build"];
  assert.equal(build.status, "crit", "cassert build must be a bottleneck");
  assert.equal(build.facts["CPU cores"], "16");
  assert.match(build.reasons[0], /enable-cassert/);
  const platform = ev.nodes["health.platform"];
  assert.equal(platform.status, "ok");
  assert.match(platform.reasons[0], /3 PostgreSQL processes: 1 client backends, 1 autovacuum workers/);
});

test("user CPU uses its own counters; causes are damped by user pressure", () => {
  const idle = artifact([
    chart("snapshot_charts_os.os_cpu_utilization", [["user", [5, 6, 5, 7]], ["system", [1, 1, 2, 1]], ["iowait", [0, 0, 0, 0]], ["idle", [94, 93, 93, 92]]]),
    chart("snapshot_charts_os.os_cpu_load", [["load1", [1, 1, 1, 1]]]),
    {item_id: "os.cpu_info", section_id: "os", collection_status: "ok", result: {kind: "plain_text", data: "CPU(s): 8\n"}},
    table("object_workload.table_workload", [{name: "schemaname", encoding: "json_string"}, {name: "relname", encoding: "json_string"}, {name: "n_live_tup", encoding: "decimal_string"}, {name: "seq_tup_read", encoding: "decimal_string"}, {name: "idx_tup_fetch", encoding: "decimal_string"}, {name: "seq_scan", encoding: "decimal_string"}], [["public", "big", "5000000", "900000000", "1000", "10"]])
  ]);
  let ev = G.evaluate(idle, definition);
  assert.equal(ev.nodes["cpu.utilization"].status, "ok");
  assert.match(ev.nodes["cpu.utilization"].reasons[0], /User CPU p95 \d+ %, mean \d+ %/);
  assert.equal(ev.nodes["cpu"].status, "ok", "idle CPU stays green even with a seq-scan cause");
  assert.ok(ev.nodes["cpu.seq_scans"].score <= 0.34, "seq scans are damped to at most 30 % on an idle CPU");
  assert.match(ev.nodes["cpu.seq_scans"].reasons[0], /public\.big/);

  const busy = artifact([
    chart("snapshot_charts_os.os_cpu_utilization", [["user", [90, 92, 95, 96]], ["system", [3, 3, 3, 3]], ["idle", [7, 5, 2, 1]]]),
    chart("snapshot_charts_os.os_cpu_load", [["load1", [20, 22, 24, 25]]]),
    {item_id: "os.cpu_info", section_id: "os", collection_status: "ok", result: {kind: "plain_text", data: "CPU(s): 8\n"}},
    idle.items["object_workload.table_workload"]
  ]);
  ev = G.evaluate(busy, definition);
  assert.equal(ev.nodes["cpu.utilization"].status, "crit");
  assert.equal(ev.nodes["cpu"].status, "crit");
  assert.equal(ev.nodes["cpu.seq_scans"].status, "crit", "the same seq scans become a bottleneck under CPU pressure");
});

test("roots take the worst child and retain missing own evidence", () => {
  const art = artifact([
    table("activity_locks.connection_pressure", [{name: "max_connections", encoding: "json_number"}, {name: "used_connections", encoding: "decimal_string"}, {name: "used_pct", encoding: "json_number"}, {name: "idle_in_transaction_connections", encoding: "decimal_string"}, {name: "waiting_connections", encoding: "decimal_string"}], [[100, "98", 98, "40", "5"]]),
    table("indexes.invalid_indexes", [{name: "index_name", encoding: "json_string"}], [["broken_idx"]])
  ], {mode: "one-shot", collection_mode: "remote-db-only"});
  const ev = G.evaluate(art, definition);
  assert.equal(ev.nodes["health.connections"].status, "crit");
  assert.equal(ev.nodes["health.invalid_objects"].status, "crit", "one invalid index carries weight 1.0");
  assert.equal(ev.nodes["database_health"].status, "crit");
  assert.equal(ev.nodes["database_health"].ownScore, null);
  assert.equal(ev.nodes["cpu.utilization"].ownStatus, "no_data");
  assert.equal(ev.nodes["disk"].status, "no_data", "no disk evidence at all in this artifact");
});

// Regression scenarios use the same column encodings and result shapes as report items.
function objectTable(itemId, rows) {
  const names = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const columns = names.map((name) => {
    const value = rows.map((row) => row[name]).find((cell) => cell !== null && cell !== undefined);
    return {name, encoding: typeof value === "boolean" ? "json_boolean" : typeof value === "number" ? "json_number" : "json_string"};
  });
  return table(itemId, columns, rows.map((row) => names.map((name) => row[name] ?? null)));
}

test("critical xmin propagates through a healthy vacuum parent to database health", () => {
  const ev = G.evaluate(artifact([
    objectTable("storage_vacuum.autovacuum_queue", [{schemaname: "public", relname: "healthy", n_live_tup: 1000000, n_dead_tup: 0, dead_tuple_vacuum_due: false, insert_vacuum_due: false, dead_tuple_overdue_factor: 0}]),
    objectTable("storage_vacuum.xmin_horizon", [{data_horizon_age_tx: 200000000}])
  ]), definition);
  assert.equal(ev.nodes["health.vacuum"].ownScore, 0);
  for (const id of ["health.vacuum.xmin", "health.vacuum", "database_health"]) {
    assert.equal(ev.nodes[id].score, 1, id);
    assert.equal(ev.nodes[id].status, "crit", id);
  }
});

test("evaluators run in post-order and max propagation retains own no_data", () => {
  const order = [];
  const def = {roots: ["root"], nodes: [
    {id: "root", evaluator: "aggregate"},
    {id: "parent", parent: "root", evaluator: "record", bindings: [{id: "x.y", role: "primary"}]},
    {id: "child", parent: "parent", evaluator: "record", bindings: [{id: "x.y", role: "primary"}]}
  ]};
  const ev = G.evaluate(artifact([objectTable("x.y", [{value: 1}])]), def, {evaluators: {
    record(ctx) { order.push(ctx.node.id); return ctx.node.id === "child" ? 1 : null; }
  }});
  assert.deepEqual(order, ["child", "parent"]);
  assert.equal(ev.nodes.parent.ownStatus, "no_data");
  assert.equal(ev.nodes.parent.status, "crit");
});

test("top_errors alone scores PANIC and supplies the real evidence source", () => {
  const ev = G.evaluate(artifact([
    objectTable("server_log.top_errors", [{message_sample: "could not write to file", severity_worst: "PANIC", sql_state: "53100", occurrences: 500}])
  ], {log_depth_time_min: 15}), definition);
  const node = ev.nodes["health.errors"];
  assert.equal(node.score, 1);
  assert.match(node.reasons.join(" "), /500/);
  assert.doesNotMatch(node.reasons.join(" "), /0 error records/);
  assert.deepEqual(node.evidence, ["server_log.top_errors"]);
});

test("log sources preserve worst severity without double-counting occurrences", () => {
  const chronology = objectTable("server_log.error_chronology", [{severity: "ERROR", repeat_count: 10}]);
  const top = objectTable("server_log.top_errors", [{severity_worst: "ERROR", occurrences: 10, message_sample: "same errors"}]);
  const ev = G.evaluate(artifact([chronology, top], {log_depth_time_min: 10}), definition);
  const node = ev.nodes["health.errors"];
  assert.equal(node.score, G.scale(1, ...G.THRESHOLDS.errorsPerMinute));
  assert.equal(node.facts["Observed log events (lower bound)"], "10");
  const panic = objectTable("server_log.top_errors", [{severity_worst: "PANIC", occurrences: 1, message_sample: "older panic omitted from chronology"}]);
  assert.equal(G.evaluate(artifact([chronology, panic]), definition).nodes["health.errors"].score, 1);
});

test("a one-point termination event chart is evidence and affects log errors", () => {
  const item = chart("server_log.query_termination_events", [["Rank 1", [500]]]);
  item.result.chart.tooltip_kind = "log_event";
  const ev = G.evaluate(artifact([item], {log_depth_time_min: 15}), definition);
  assert.equal(G.itemPresence(item), "present");
  assert.equal(ev.nodes["health.errors"].score, 1);
  assert.equal(ev.nodes["health.errors"].facts["Query terminations"], "500");
  assert.ok(ev.nodes["health.errors"].evidence.includes(item.item_id));
  assert.equal(G.itemPresence(chart("snapshot_charts_os.os_cpu_load", [["load1", [10]]])), "empty");
});

test("caught-up standby does not turn red because the primary is idle", () => {
  for (const seconds of [60, 3600, 86400]) {
    const ev = G.evaluate(artifact([
      objectTable("replication.standby_recovery_state", [{in_recovery: true, replay_paused: false, receive_replay_lag_bytes: 0, seconds_since_last_replayed_xact: seconds}]),
      chart("snapshot_charts_db.standby_replay_delay", [["delay", [seconds, seconds, seconds]]]),
      chart("snapshot_charts_db.standby_replay_lag_bytes", [["lag", [0, 0, 0]]])
    ]), definition);
    assert.equal(ev.nodes["health.replication"].score, 0);
  }
});

test("replication still scores unapplied WAL and paused replay", () => {
  const lagging = objectTable("replication.standby_recovery_state", [{in_recovery: true, replay_paused: false, receive_replay_lag_bytes: 1073741824, seconds_since_last_replayed_xact: 120}]);
  assert.equal(G.evaluate(artifact([lagging]), definition).nodes["health.replication"].score, 1);
  const paused = objectTable("replication.standby_recovery_state", [{in_recovery: true, replay_paused: true, receive_replay_lag_bytes: 0, seconds_since_last_replayed_xact: 3600}]);
  assert.equal(G.evaluate(artifact([paused]), definition).nodes["health.replication"].status, "warn");
});

test("replay age requires byte-lag evidence from the same chart timestamps", () => {
  const delay = chart("snapshot_charts_db.standby_replay_delay", [["delay", [120, 120, 120]]]);
  assert.equal(G.evaluate(artifact([delay]), definition).nodes["health.replication"].ownStatus, "no_data");
  const lag = chart("snapshot_charts_db.standby_replay_lag_bytes", [["lag", [1024, 1024, 1024]]]);
  assert.equal(G.evaluate(artifact([delay, lag]), definition).nodes["health.replication"].score, 1);
  const mismatched = structuredClone(lag);
  for (const point of mismatched.result.series[0].points) point.t = point.t.replace("00:00:", "01:00:");
  assert.equal(G.evaluate(artifact([delay, mismatched]), definition).nodes["health.replication"].score, 0);
  const ageOnly = objectTable("replication.standby_recovery_state", [{in_recovery: true, replay_paused: false, receive_replay_lag_bytes: null, seconds_since_last_replayed_xact: 3600}]);
  assert.equal(G.evaluate(artifact([ageOnly]), definition).nodes["health.replication"].ownStatus, "no_data");
});

for (const [eventType, message] of [
  ["ready", "database system is ready to accept connections"],
  ["configuration_reload", "received SIGHUP, reloading configuration files"],
  ["recovery_redo", "redo starts at 0/1000000"],
  ["recovery_complete", "redo done at 0/1000000"],
  ["recovery_wal_end", "invalid record length at 0/1000000: expected at least 24, got 0"]
]) {
  test("observational lifecycle marker is not a crash: " + eventType, () => {
    const ev = G.evaluate(artifact([objectTable("server_log.server_lifecycle", [{event_type: eventType, severity: "LOG", sql_state: "00000", occurrences: 1, message}])]), definition);
    assert.equal(ev.nodes["health.crashes"].score, 0);
  });
}

test("generic missing-file incident does not imply a crash, OOM or disk-full", () => {
  const ev = G.evaluate(artifact([objectTable("server_log.system_incidents", [{incident_type: "missing_file", severity: "ERROR", sql_state: "58P01", message: 'could not open file "/review-file-that-does-not-exist" for reading: No such file or directory', occurrences: 1}])]), definition);
  for (const id of ["health.crashes", "ram.pressure", "disk.space"]) {
    assert.ok(ev.nodes[id].score === null || ev.nodes[id].score === 0, id);
  }
});

for (const [kind, target] of [["out_of_memory", "ram.pressure"], ["disk_full", "disk.space"], ["data_corruption", "health.crashes"], ["index_corruption", "health.crashes"], ["checksum_failure", "health.crashes"]]) {
  test("typed system incident reaches only the appropriate branch: " + kind, () => {
    const ev = G.evaluate(artifact([objectTable("server_log.system_incidents", [{incident_type: kind, severity: "ERROR", occurrences: 1}])]), definition);
    assert.equal(ev.nodes[target].status, "crit");
    assert.ok(ev.nodes[target].evidence.includes("server_log.system_incidents"));
    for (const id of ["ram.pressure", "disk.space", "health.crashes"].filter((id) => id !== target)) {
      assert.ok(ev.nodes[id].score === null || ev.nodes[id].score === 0, id);
    }
  });
}

test("actual crash markers remain critical but SIGKILL alone does not prove OOM", () => {
  const ev = G.evaluate(artifact([
    objectTable("server_log.server_lifecycle", [{event_type: "backend_crash", severity: "LOG", occurrences: 1, message: "server process was terminated by signal 9"}]),
    objectTable("server_log.crash_recovery_events", [{message: "server process was terminated by signal 9", repeat_count: 1, severity: "LOG"}])
  ]), definition);
  assert.equal(ev.nodes["health.crashes"].status, "crit");
  assert.equal(ev.nodes["ram.pressure"].ownStatus, "no_data");
  const redo = objectTable("server_log.crash_recovery_events", [{message: "redo starts at 0/1000000", repeat_count: 1, severity: "LOG"}]);
  assert.equal(G.evaluate(artifact([redo]), definition).nodes["health.crashes"].score, 0);
});

test("user CPU excludes iowait and steal, which have separate branches", () => {
  const parts = [["user", [1, 1, 1]], ["system", [0, 0, 0]], ["iowait", [95, 95, 95]]];
  for (const series of [parts, parts.concat([["idle", [4, 4, 4]]])]) {
    const ev = G.evaluate(artifact([chart("snapshot_charts_os.os_cpu_utilization", series)]), definition);
    assert.equal(ev.nodes["cpu.utilization"].score, 0);
    assert.equal(ev.nodes["cpu.utilization"].facts["User CPU p95"], "1 %");
    assert.equal(ev.nodes["cpu.iowait"].ownStatus, "crit");
    assert.equal(ev.nodes["cpu.system_time"].ownStatus, "ok");
  }
  const steal = chart("snapshot_charts_os.os_cpu_utilization", [["user", [1, 1, 1]], ["idle", [79, 79, 79]], ["steal", [20, 20, 20]]]);
  const ev = G.evaluate(artifact([steal]), definition);
  assert.equal(ev.nodes["cpu.utilization"].facts["User CPU p95"], "1 %");
  assert.equal(ev.nodes["cpu.utilization"].status, "ok");
  assert.equal(ev.nodes["cpu.steal"].status, "crit", "steal is a separate resource problem");
});

test("deadlock chart and endpoint delta are overlapping sources, not additive", () => {
  const events = chart("snapshot_charts_db.database_deadlocks", [["deadlocks (db)", [0, 1, 1, 0]]]);
  const delta = objectTable("snapshot_delta_workload.database_workload_delta", [{datname: "db", deadlocks_delta: 2}]);
  const nodes = [[events], [delta], [events, delta]].map((items) => G.evaluate(artifact(items), definition).nodes["health.locks"]);
  for (const node of nodes) {
    assert.equal(node.status, "warn");
    assert.equal(node.score, nodes[0].score);
    assert.match(node.reasons.join(" "), /2 deadlock/);
  }
  assert.deepEqual(nodes[1].evidence, ["snapshot_delta_workload.database_workload_delta"]);
});

test("resource trees start with symptoms and keep candidate evidence underneath", () => {
  const byId = Object.fromEntries(definition.nodes.map(node => [node.id, node]));
  const children = id => definition.nodes.filter(node => node.parent === id).map(node => node.id);
  assert.deepEqual(children("cpu"), ["cpu.utilization", "cpu.system_time", "cpu.iowait", "cpu.steal"]);
  assert.deepEqual(children("ram"), ["ram.pressure", "ram.swap", "ram.cache_efficiency"]);
  assert.deepEqual(children("disk"), ["disk.saturation", "disk.read", "disk.write", "disk.space"]);
  assert.deepEqual(children("cpu.iowait"), ["cpu.iowait.read", "cpu.iowait.write", "cpu.iowait.swap"]);
  assert.equal(byId["disk.bloat"].parent, "disk.space");
  for (const id of ["cpu.iowait.read.queries.scans", "cpu.iowait.write.data.checkpoints", "cpu.iowait.write.temp_files"]) {
    assert.equal(byId[id].pressure, "cpu_iowait");
    assert.ok(byId[id].bindings.length);
  }
  for (const node of definition.nodes) {
    if (node.pressure) assert.ok(["cpu_user", "cpu_system", "cpu_iowait", "ram", "disk"].includes(node.pressure));
  }
});

test("I/O wait colors I/O contributors independently of idle user CPU", () => {
  const scans = objectTable("object_workload.table_workload", [{schemaname: "public", relname: "big", n_live_tup: 5000000, seq_tup_read: 900000000, idx_tup_fetch: 1000, seq_scan: 10}]);
  const cpu = chart("snapshot_charts_os.os_cpu_utilization", [["user", [1, 1, 1]], ["system", [0, 0, 0]], ["iowait", [95, 95, 95]]]);
  const art = artifact([cpu, scans]);
  for (const roots of [definition.roots, definition.roots.slice().reverse()]) {
    const ev = G.evaluate(art, {...definition, roots});
    assert.equal(ev.nodes["cpu.utilization"].status, "ok");
    assert.equal(ev.nodes["cpu.seq_scans"].status, "ok");
    assert.equal(ev.nodes["cpu.iowait"].ownStatus, "crit");
    const contributor = ev.nodes["cpu.iowait.read.queries.scans"];
    assert.equal(contributor.status, "crit");
    assert.match(contributor.reasons.join(" "), /public\.big/);
    assert.ok(contributor.bindings.some(binding => binding.id === "object_workload.table_workload"));
    assert.equal(ev.nodes["disk.saturation"].status, "no_data", "I/O wait does not prove device saturation");
  }
});

test("system and user CPU use separate pressure and include IRQ and nice counters", () => {
  const packets = chart("snapshot_charts_os.os_network_packets", [["rx (eth0)", [300000, 300000, 300000]]]);
  for (const [user, system, irq, expectedUser, expectedSystem] of [[95, 0, 0, "crit", "ok"], [1, 20, 10, "ok", "crit"]]) {
    const cpu = chart("snapshot_charts_os.os_cpu_utilization", [["user", [user, user, user]], ["system", [system, system, system]], ["irq", [irq, irq, irq]], ["iowait", [0, 0, 0]]]);
    const ev = G.evaluate(artifact([cpu, packets]), definition);
    assert.equal(ev.nodes["cpu.utilization"].status, expectedUser);
    assert.equal(ev.nodes["cpu.system_time"].status, expectedSystem);
    assert.equal(ev.nodes["cpu.network"].status, expectedSystem);
  }
  const nice = chart("snapshot_charts_os.os_cpu_utilization", [["user", [1, 1, 1]], ["nice", [95, 95, 95]]]);
  assert.equal(G.evaluate(artifact([nice]), definition).nodes["cpu.utilization"].ownStatus, "crit");
});

test("load alone and unpaired component samples do not manufacture CPU work", () => {
  const load = chart("snapshot_charts_os.os_cpu_load", [["load1", [100, 100, 100]]]);
  assert.equal(G.evaluate(artifact([load]), definition).nodes["cpu.utilization"].ownStatus, "no_data");
  const cpu = chart("snapshot_charts_os.os_cpu_utilization", [["user", [1, 1, 1]], ["nice", [98, 98, 98]]]);
  cpu.result.series[1].points.forEach(point => { point.t = point.t.replace("00:00:", "01:00:"); });
  assert.equal(G.evaluate(artifact([cpu]), definition).nodes["cpu.utilization"].ownStatus, "no_data");
});

test("swap and available memory are independent, occupancy is not active paging", () => {
  const memory = objectTable("os.memory_info", [{metric: "MemTotal", value_normalized: 1000}, {metric: "MemAvailable", value_normalized: 800}, {metric: "SwapTotal", value_normalized: 100}, {metric: "SwapFree", value_normalized: 20}]);
  const ev = G.evaluate(artifact([memory]), definition);
  assert.equal(ev.nodes["ram.pressure"].ownStatus, "ok");
  assert.equal(ev.nodes["ram.swap"].ownStatus, "crit");
  assert.match(ev.nodes["ram.swap"].reasons.join(" "), /does not establish active paging/);
  assert.equal(ev.nodes["cpu.iowait"].ownStatus, "no_data");
});

test("throughput without latency does not establish healthy disk I/O", () => {
  const reads = chart("snapshot_charts_os.os_disk_read_throughput", [["read (nvme0n1)", [1000000, 1000000, 1000000]]]);
  const ev = G.evaluate(artifact([reads]), definition);
  assert.equal(ev.nodes["disk.read"].ownStatus, "no_data");
  assert.equal(ev.nodes["disk.saturation"].ownStatus, "no_data");
});

test("bloat explanations survive reuse and root traversal order", () => {
  const art = artifact([objectTable("storage_vacuum.table_bloat_candidates", [{schema_name: "public", table_name: "bloated", can_estimate: true, wasted_bytes: 1073741824, bloat_percent: 80}])]);
  for (const roots of [definition.roots, definition.roots.slice().reverse()]) {
    const ev = G.evaluate(art, {...definition, roots});
    for (const id of ["disk.bloat", "health.vacuum"]) {
      const node = ev.nodes[id];
      assert.equal(node.score, 1, id);
      assert.match(node.reasons.join(" "), /public\.bloated.*80 %/);
      assert.ok(node.evidence.includes("storage_vacuum.table_bloat_candidates"));
    }
  }
});

test("post-order pressure caches retain explanations on parents and causes", () => {
  const art = artifact([
    objectTable("os.memory_info", [{metric: "MemTotal", value_normalized: 1000}, {metric: "MemAvailable", value_normalized: 20}]),
    objectTable("overview.pg_settings", [{setting_name: "work_mem", setting_value: "10", setting_normalized: 10}, {setting_name: "max_connections", setting_value: "100", setting_normalized: 100}]),
    chart("snapshot_charts_os.os_disk_latency", [["await (nvme0n1)", [20, 20, 20]]]),
    chart("snapshot_charts_db.checkpoint_trigger_events", [["requested", [1, 1, 1]], ["timed", [0, 0, 0]]])
  ]);
  const ev = G.evaluate(art, definition);
  for (const id of ["ram.pressure", "ram.work_mem"]) {
    const node = ev.nodes[id];
    assert.equal(node.score, 1, id);
    assert.match(node.reasons.join(" "), /MemAvailable/);
    assert.ok(node.evidence.includes("os.memory_info"));
    assert.equal(node.reasons.length, new Set(node.reasons).size, "cached reasons are not duplicated");
  }
  for (const id of ["disk.saturation", "disk.write.checkpoints"]) {
    assert.equal(ev.nodes[id].score, 1, id);
    assert.match(ev.nodes[id].reasons.join(" "), /await p95 20.0 ms/);
    assert.ok(ev.nodes[id].evidence.includes("snapshot_charts_os.os_disk_latency"));
  }
});

test("empty items count as checked, skipped and absent items produce hints", () => {
  const art = artifact([
    table("activity_locks.lock_waits", ["blocked_pid"], []),
    table("activity_locks.blocking_lock_tree", ["pid"], []),
    table("maintenance_progress.vacuum_progress", ["pid"], []),
    table("maintenance_progress.create_index_progress", ["pid"], []),
    table("maintenance_progress.cluster_progress", ["pid"], []),
    table("maintenance_progress.copy_progress", ["pid"], []),
    {item_id: "os.sudoers_postgres_escalation", section_id: "os", collection_status: "unsupported", reason: "The collector cannot read sudoers"}
  ], {mode: "one-shot", collection_mode: "remote-db-only"});
  const ev = G.evaluate(art, definition);
  assert.equal(ev.nodes["health.locks"].status, "ok");
  assert.match(ev.nodes["health.locks"].reasons[0], /No lock waits/);
  assert.equal(ev.nodes["health.maintenance"].status, "ok");
  assert.equal(ev.nodes["cpu.utilization"].status, "no_data");
  assert.ok(ev.nodes["cpu.utilization"].hints.some((hint) => /snapshots mode/.test(hint)));
  assert.ok(ev.nodes["cpu.utilization"].hints.some((hint) => /remote-db-only/.test(hint)));
  assert.ok(ev.nodes["security.host"].hints.some((hint) => /cannot read sudoers/.test(hint)));
  assert.ok(ev.nodes["health.errors"].hints.some((hint) => /--log-depth-time-min/.test(hint)));
});

test("checkpoint evaluator derives timed checkpoints from completed on PostgreSQL 18", () => {
  const art = artifact([
    chart("snapshot_charts_db.checkpoint_trigger_events", [["completed", [0, 1, 0, 1, 0, 1]], ["requested", [0, 1, 0, 1, 0, 1]]]),
    chart("snapshot_charts_os.os_disk_latency", [["await (nvme0n1)", [30, 35, 40, 45, 50, 55]]])
  ]);
  const ev = G.evaluate(art, definition);
  const node = ev.nodes["disk.write.checkpoints"];
  assert.match(node.reasons[0], /3 requested and 0 timed checkpoints/);
  assert.equal(node.status, "crit", "all-requested checkpoints on a saturated disk");
  assert.equal(ev.nodes["disk.saturation"].status, "crit");
});

test("memory pressure reads MemAvailable and swap; huge pages flag THP", () => {
  const art = artifact([
    table("os.memory_info", [{name: "metric", encoding: "json_string"}, {name: "value_normalized", encoding: "decimal_string"}], [["MemTotal", "1000"], ["MemAvailable", "20"], ["SwapTotal", "100"], ["SwapFree", "40"]]),
    table("os.postgresql_huge_pages", [{name: "huge_pages_actual", encoding: "json_string"}, {name: "shared_memory_size_bytes", encoding: "decimal_string"}, {name: "transparent_huge_pages_mode", encoding: "json_string"}, {name: "host_page_tables_pct_ram", encoding: "json_number"}], [["off", "8589934592", "always", 0.5]])
  ], {mode: "one-shot"});
  const ev = G.evaluate(art, definition);
  assert.equal(ev.nodes["ram.pressure"].status, "crit");
  assert.match(ev.nodes["ram.pressure"].reasons.join(" "), /MemAvailable/);
  assert.match(ev.nodes["ram.swap"].reasons.join(" "), /Swap used 60 %/);
  assert.equal(ev.nodes["ram.huge_pages"].status, "warn");
  assert.match(ev.nodes["ram.huge_pages"].reasons.join(" "), /huge_pages are off/);
  assert.match(ev.nodes["ram.huge_pages"].reasons.join(" "), /transparent_hugepage = always/);
});

test("generic findings use the worst risk_level row and the binding weight otherwise", () => {
  const art = artifact([
    table("cluster_inventory.pg_hba_insecure_auth_methods", [{name: "auth_method", encoding: "json_string"}, {name: "risk_level", encoding: "json_string"}], [["trust", "high"], ["md5", "medium"]]),
    table("os.postgres_env_secret_leaks", [{name: "pid", encoding: "json_number"}], [[1]]),
    table("os.core_dump_policy", [{name: "setting", encoding: "json_string"}, {name: "risk_level", encoding: "json_string"}], [["kernel.core_pattern", "low"]])
  ], {mode: "one-shot"});
  const ev = G.evaluate(art, definition);
  assert.equal(ev.nodes["security.authentication"].status, "crit");
  assert.match(ev.nodes["security.authentication"].reasons[0], /worst risk high/);
  assert.equal(ev.nodes["security.host"].status, "crit", "one leaked secret is critical regardless of the row count");
  assert.equal(ev.nodes["database_security"].status, "crit");
});

test("lab snapshots fixture evaluates every node without errors and with data", () => {
  const ev = G.evaluate(fixture("lab_snapshots.json"), definition);
  assert.equal(ev.order.length, definition.nodes.length);
  for (const nodeId of ev.order) assert.equal(ev.nodes[nodeId].error, null, nodeId);
  assert.equal(ev.coverage.rootsWithData, 5);
  assert.deepEqual(ev.order.filter(id => ev.nodes[id].status === "no_data"), ["cpu.steal"], "the lab has no steal counter");
  assert.equal(ev.nodes["cpu"].status, "ok");
  assert.equal(ev.nodes["database_security"].status, "crit");
  assert.ok(ev.nodes["disk.saturation"].reasons[0].includes("nvme0n1 (nvme)"));
  assert.ok(ev.links.length > 0);
  assert.ok(ev.nodes["disk.bloat"].causes.some((link) => link.to === "health.vacuum"));
});

test("one-shot remote-db-only fixture greys out resource roots and explains why", () => {
  const ev = G.evaluate(fixture("lab_one_shot_remote_db_only.json"), definition);
  assert.equal(ev.coverage.runMode, "one-shot");
  // Resource nodes have no evidence of their own; their color is a proxy from children.
  assert.equal(ev.nodes["cpu.utilization"].ownStatus, "no_data");
  assert.equal(ev.nodes["disk.saturation"].ownStatus, "no_data");
  assert.equal(ev.nodes["ram.pressure"].ownStatus, "no_data");
  assert.ok(ev.nodes["cpu.utilization"].hints.some((hint) => /snapshots/.test(hint)));
  assert.ok(ev.nodes["disk.saturation"].hints.some((hint) => /snapshots/.test(hint)));
  assert.ok(ev.nodes["security.host"].hints.some((hint) => /remote-db-only/.test(hint)));
  assert.notEqual(ev.nodes["database_security"].status, "no_data");
  assert.notEqual(ev.nodes["database_health"].status, "no_data");
  assert.ok(ev.coverage.nodesWithoutData > 5);
});
