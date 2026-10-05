"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const G = require("../../src/pg_diag/render/graph/pg-diag-graph.js");
const definition = require("../../src/pg_diag/render/graph/graph.json");

const start = "2026-09-05T00:00:00Z", finish = "2026-09-05T01:00:00Z";
function table(id, rows, extra = {}) {
  return {item_id: id, collection_status: rows.length ? "ok" : "empty", result: {
    kind: "table", columns: [...new Set(rows.flatMap(Object.keys))].map(name => ({name, encoding: "json_value"})),
    rows, row_count: rows.length, ...extra
  }};
}
function chart(id, series, extra = {}, offset = 0) {
  return {item_id: id, collection_status: "ok", result: {kind: "chart",
    series: Object.entries(series).map(([name, values]) => ({name, points: values.map((value, n) => ({
      t: new Date(Date.parse(start) + (offset + n) * 1000).toISOString(), value
    }))})), ...extra
  }};
}
function evaluate(items, runtime = {}) {
  const nodes = G.evaluate({items: Object.fromEntries(items.map(i => [i.item_id, i])), runtime: {
    mode: "snapshots", collection_mode: "local", duration_seconds: 3600, log_depth_time_min: 60, ...runtime
  }}, definition).nodes;
  for (const node of Object.values(nodes)) assert.equal(node.error, null, node.id);
  return nodes;
}
const disk = () => chart("snapshot_charts_os.os_disk_latency", {"await (sda)": [100, 100]});
const checkpointChart = () => chart("snapshot_charts_db.checkpoint_trigger_events", {requested: [5, 5], timed: [0, 1]});
const coverage = () => ({snapshot_window_started_at: start, snapshot_window_finished_at: finish,
  log_collection: {status: "collected", coverage: {
    ranking_complete: true, window_truncated: false, covered_from: start, covered_to: finish
  }}});
const checkpointLog = () => table("server_log.checkpoints", [
  {event: "checkpoint", phase: "starting", reason: "immediate force wait", repeat_count: 10,
    log_time: start, last_time: "2026-09-05T00:01:00Z", count_complete: true},
  {event: "checkpoint", phase: "starting", reason: "time", repeat_count: 1, log_time: finish, count_complete: true}
], {omitted_series_count: 0});

test("storage I/O incidents reach the disk root even with ample free space", () => {
  for (const row of [
    {incident_type: "io_error", sql_state: "58030", message: 'could not fsync file "base/1/123": Input/output error'},
    ...["fsync_failure", "write_failure", "read_failure", "disk_full"].map(incident_type => ({incident_type})),
    {sql_state: "58030", message: "ошибка ввода-вывода"},
    {message: 'could not write to file "base/1/123": Read-only file system'}
  ]) {
    const incident = table("server_log.system_incidents", [{severity: "ERROR", occurrences: 1, count_complete: true, ...row}]);
    const nodes = evaluate([incident, table("os.disk_usage", [{mount_point: "/pgdata", used_pct: 40}])]);
    for (const id of ["disk.space.sources.incidents", "disk.space", "disk"]) assert.equal(nodes[id].status, "crit", id + JSON.stringify(row));
    assert.ok(nodes["disk.space.sources.incidents"].evidence.includes(incident.item_id));
    assert.doesNotMatch(nodes["disk.space.sources.incidents"].reasons.join(" "), /No .*failure found/);
  }
  for (const row of [
    {incident_type: "missing_file", sql_state: "58P01", message: 'could not read file "missing": No such file or directory'},
    {sql_state: "42P01", message: 'relation "could not fsync file" does not exist'},
    {incident_type: "too_many_connections", sql_state: "53300"}
  ]) assert.equal(evaluate([table("server_log.system_incidents", [row])])["disk.space.sources.incidents"].status, "ok");
  const failed = table("server_log.system_incidents", [{incident_type: "io_error"}]);
  failed.collection_status = "error";
  assert.equal(evaluate([failed])["disk.space.sources.incidents"].status, "no_data");
});

test("checkpoint parents and timing directions use the same completed-operation denominator", () => {
  for (const [checkpoints, restartpoints, sync, expected] of [
    [1, 9, 15000, "ok"], [0, 3, 6000, "warn"], [0, 3, 30000, "crit"],
    [0, 0, 0, "ok"], [1, null, 20000, "no_data"], [-1, 3, 6000, "no_data"],
    [1, 0, -100, "no_data"], [0, 0, 100, "no_data"]
  ]) {
    const nodes = evaluate([disk(), chart("snapshot_charts_os.os_cpu_utilization", {iowait: [40, 40]}),
      table("snapshot_delta_workload.checkpointer_delta", [{checkpoints_done_delta: checkpoints,
        restartpoints_done_delta: restartpoints, sync_time_ms_delta: sync}])]);
    for (const id of ["disk.write.checkpoints", "cpu.iowait.write.data.checkpoints"]) {
      assert.equal(nodes[id].ownStatus, expected, id + JSON.stringify([checkpoints, restartpoints, sync]));
      assert.equal(nodes[id + ".sources.timing"].status, expected);
      if (checkpoints === 1 && restartpoints === 9) assert.match(nodes[id].reasons.join(" "), /1\.50 s/);
    }
  }
});

test("current logical replication deltas supersede historical failures in parents and directions", () => {
  const workers = () => table("replication.subscription_workers", [{subname: "healthy", subenabled: true,
    worker_running: true, apply_error_count: 100, sync_error_count: 2, conflict_count: 100}]);
  for (const [deltaRows, expected] of [
    [[{apply_error_count_delta: 0, sync_error_count_delta: 0, conflict_count_delta: 0}], "ok"],
    [[{apply_error_count_delta: 1, sync_error_count_delta: 0, conflict_count_delta: 1}], "warn"],
    [[{apply_error_count_delta: null, sync_error_count_delta: null, conflict_count_delta: null}], "warn"],
    [[{apply_error_count_delta: -1, sync_error_count_delta: 0, conflict_count_delta: 0}], "warn"],
    [[], "warn"]
  ]) {
    const nodes = evaluate([workers(), table("snapshot_delta_workload.subscription_errors_conflicts_delta", deltaRows)]);
    for (const id of ["health.replication", "health.replication.sources.logical", "database_health"]) assert.equal(nodes[id].status, expected, id + JSON.stringify(deltaRows));
    if (expected === "ok") {
      assert.equal(nodes["health.replication"].ownScore, 0);
      assert.equal(nodes["health.replication"].facts["Apply errors in window"], "0");
      assert.doesNotMatch(nodes["health.replication"].reasons.join(" "), /100 logical replication/);
    } else assert.ok(nodes["health.replication"].reasons.some(r => /in window|since statistics reset/.test(r)));
  }
  const failed = table("snapshot_delta_workload.subscription_errors_conflicts_delta", [{apply_error_count_delta: 0, sync_error_count_delta: 0, conflict_count_delta: 0}]);
  failed.collection_status = "error";
  assert.equal(evaluate([workers(), failed])["health.replication"].status, "warn");
  const invalidWindow = table("snapshot_delta_workload.subscription_errors_conflicts_delta", [{apply_error_count_delta: 0, sync_error_count_delta: 0, conflict_count_delta: 0}], {delta_window: {duration_seconds: 0}});
  assert.equal(evaluate([workers(), invalidWindow])["health.replication"].status, "warn");
});

test("partial logical replication deltas preserve observed errors without proving healthy zeros", () => {
  for (const [count, expected] of [[1, "warn"], [0, "no_data"]]) {
    const nodes = evaluate([
      table("replication.subscription_workers", [{subname: "healthy", subenabled: true, worker_running: true,
        apply_error_count: 0, sync_error_count: 0, conflict_count: 0}]),
      table("snapshot_delta_workload.subscription_errors_conflicts_delta", [
        {apply_error_count_delta: count, sync_error_count_delta: 0, conflict_count_delta: 0},
        {apply_error_count_delta: null, sync_error_count_delta: null, conflict_count_delta: null}])
    ]);
    for (const id of ["health.replication", "health.replication.sources.logical"]) {
      assert.equal(nodes[id].status, expected);
      assert.ok(nodes[id].hints.some(h => /lack a valid window delta/.test(h)));
    }
  }
});

test("hot buffers alone do not prove cache undersizing, while measured misses still warn", () => {
  const buffers = () => [chart("buffer_cache.utilization", {used: [90, 90], unused: [10, 10]}),
    chart("buffer_cache.usage_count_distribution", {"usage count 0": [10, 10], "usage count 5": [90, 90]})];
  const healthy = evaluate([...buffers(), chart("snapshot_charts_db.database_block_access_rate", {"hit (db)": [1000, 1000], "read (db)": [0, 0]})]);
  assert.equal(healthy["ram.shared_buffers"].ownScore, null, "reuse without a sizing criterion is informational");
  assert.equal(healthy.ram.status, "ok");
  assert.equal(healthy["ram.shared_buffers"].facts["Buffers with usage count >= 3"], "90 %");
  assert.doesNotMatch(healthy["ram.shared_buffers"].reasons.join(" "), /working set exceeds/);
  const misses = evaluate([...buffers(), chart("snapshot_charts_db.database_block_access_rate", {"hit (db)": [800, 800], "read (db)": [200, 200]})]);
  assert.equal(misses["ram.cache_efficiency"].ownStatus, "crit");
  assert.equal(misses.ram.status, "crit");
});

test("checkpoint logs replace snapshot counts only with complete matching coverage", () => {
  for (const defect of ["short", "truncated", "ranking", "capped", "old", "incomplete_count", "crossing_rle", "insufficient_count"]) {
    const runtime = coverage(), log = checkpointLog();
    if (defect === "short") runtime.log_collection.coverage.covered_from = "2026-09-05T00:50:00Z";
    if (defect === "truncated") runtime.log_collection.coverage.window_truncated = true;
    if (defect === "ranking") runtime.log_collection.coverage.ranking_complete = false;
    if (defect === "capped") log.result.omitted_series_count = 20;
    if (defect === "old") delete log.result.omitted_series_count;
    if (defect === "incomplete_count") log.result.rows[0].count_complete = false;
    if (defect === "crossing_rle") log.result.rows[0].log_time = "2026-09-04T23:59:59Z";
    if (defect === "insufficient_count") log.result.rows[0].repeat_count = 1;
    assert.equal(evaluate([checkpointChart(), log, disk()], runtime)["disk.write.checkpoints"].status, "crit", defect);
  }
  assert.equal(evaluate([checkpointChart(), checkpointLog(), disk()], coverage())["disk.write.checkpoints"].status, "ok");
});

test("checkpoint reasons outside the snapshot and restartpoints cannot explain requested checkpoints", () => {
  for (const defect of ["outside", "restartpoint"]) {
    const log = checkpointLog();
    if (defect === "outside") Object.assign(log.result.rows[0], {log_time: "2026-09-04T23:00:00Z", last_time: "2026-09-04T23:01:00Z"});
    else log.result.rows[0].event = "restartpoint";
    assert.equal(evaluate([checkpointChart(), log, disk()], coverage())["disk.write.checkpoints"].status, "crit");
  }
  const cumulative = table("wal_io_checkpoints.checkpointer", [{num_requested: 100, num_timed: 1}]);
  assert.equal(evaluate([cumulative, checkpointLog(), disk()], coverage())["disk.write.checkpoints"].status, "crit",
    "log window cannot replace statistics since reset");
});

test("hidden OS zeros require enough samples, no gaps and no sampler failure", () => {
  for (const [id, name, nodeId] of [
    ["snapshot_charts_os.os_cpu_utilization", "user", "cpu.utilization"],
    ["snapshot_charts_os.os_network_errors", "rx errors (eth0)", "network.interfaces.errors"]
  ]) {
    for (const defect of ["valid", "one", "missing", "legacy_gap", "warning", "failed"]) {
      const item = chart(id, {}, {sample_count: 3, zero_series: [{name, sample_count: 3, missing_count: 0}]});
      if (defect === "one") item.result.zero_series[0].sample_count = 1;
      if (defect === "missing") item.result.zero_series[0].missing_count = 2;
      if (defect === "legacy_gap") item.result.sample_count = 5;
      if (defect === "warning") item.diagnostics = [{level: "warning", code: "sampler", message: "Host sampler failed"}];
      if (defect === "failed") item.collection_status = "error";
      assert.equal(evaluate([item])[nodeId].ownStatus, defect === "valid" ? "ok" : "no_data", id + " " + defect);
    }
  }
});

test("a hidden main CPU counter does not erase a measured supplementary counter", () => {
  const item = chart("snapshot_charts_os.os_cpu_utilization", {nice: [95, 95]}, {
    sample_count: 2, zero_series: [{name: "user", sample_count: 2, missing_count: 0}]
  });
  assert.equal(evaluate([item])["cpu.utilization"].ownStatus, "crit");
});

test("session rates use delta duration and reject an invalid explicit window", () => {
  const item = table("snapshot_delta_workload.database_session_outcomes_delta", [{sessions_delta: 1200}], {
    delta_window: {start_time: start, finish_time: "2026-09-05T00:01:00Z", duration_seconds: 60}
  });
  const nodes = evaluate([item], {duration_seconds: 30});
  assert.equal(nodes["network.clients.churn"].facts["New sessions per second"], "20.00");
  assert.ok(Object.values(nodes).some(node => node.facts["Sessions per second"] === "20.0"), "CPU churn uses the same denominator");
  item.result.delta_window.duration_seconds = 0;
  assert.equal(evaluate([item], {duration_seconds: 30})["network.clients.churn"].status, "no_data");
  delete item.result.delta_window;
  assert.equal(evaluate([item], {duration_seconds: 30, snapshot_window_started_at: start,
    snapshot_window_finished_at: "2026-09-05T00:01:00Z"})["network.clients.churn"].facts["New sessions per second"], "20.00");
});

test("packet pressure requires simultaneous kernel CPU pressure", () => {
  const packets = chart("snapshot_charts_os.os_network_packets", {rx: [...Array(10).fill(500000), ...Array(10).fill(100)]});
  const cpu = chart("snapshot_charts_os.os_cpu_utilization", {system: [...Array(10).fill(1), ...Array(10).fill(30)]});
  assert.equal(evaluate([packets, cpu])["network.traffic.packets"].status, "ok");
  const coincident = chart("snapshot_charts_os.os_cpu_utilization", {system: Array(20).fill(30)});
  assert.equal(evaluate([packets, coincident])["network.traffic.packets"].status, "crit");
  const shifted = chart("snapshot_charts_os.os_cpu_utilization", {system: Array(20).fill(30)}, {}, 100);
  assert.equal(evaluate([packets, shifted])["network.traffic.packets"].status, "no_data");
  const sparse = chart("snapshot_charts_os.os_cpu_utilization", {system: [30, ...Array(19).fill(null)]});
  assert.equal(evaluate([packets, sparse])["network.traffic.packets"].status, "no_data");
});

test("receive pressure excludes WAL already written but waiting for local flush", () => {
  const row = {status: "streaming", latest_end_lsn: "1/80000000", written_lsn: "1/80000000",
    flushed_lsn: "1/0", receive_lag_bytes: 2147483648};
  const nodes = evaluate([table("replication.wal_receiver", [row])]);
  assert.equal(nodes["network.replication.receive"].status, "ok");
  assert.equal(nodes["network.replication.receive"].facts["Written WAL awaiting local flush"], "2.0 GiB");
  assert.equal(nodes["health.replication"].status, "crit", "flush lag still matters for replication health");
  assert.equal(evaluate([table("replication.wal_receiver", [{...row, written_lsn: "1/0"}])])["network.replication.receive"].status, "crit");
  for (const written_lsn of [undefined, "invalid", "1/FFFFFFFF"]) {
    const node = evaluate([table("replication.wal_receiver", [{...row, written_lsn}])])["network.replication.receive"];
    assert.equal(node.status, "ok", "streaming status remains usable without attributing the flush gap to transport");
    assert.match(node.reasons.join(" "), /cannot isolate receive pressure/);
  }
  const rollover = {...row, latest_end_lsn: "2/0", written_lsn: "1/80000000"};
  assert.equal(evaluate([table("replication.wal_receiver", [rollover])])["network.replication.receive"].status, "crit");
});

test("known SQLSTATE overrides message text and fallback signatures are anchored", () => {
  for (const sql_state of ["42P01", null]) {
    for (const message of ['relation "out of memory" does not exist', 'column "deadlock detected" does not exist', 'relation "could not write to file" does not exist']) {
      const item = table("server_log.error_chronology", [{severity: "ERROR", sql_state, message, repeat_count: 1}]);
      assert.equal(evaluate([item])["health.errors"].score, 0.1);
    }
  }
  for (const [sql_state, message, status] of [
    ["42P01", "out of memory", "ok"], [null, "out of memory", "crit"],
    ["53200", "не хватает памяти", "crit"], [null, 'could not write to file "x": No space left on device', "crit"]
  ]) assert.equal(evaluate([table("server_log.error_chronology", [{severity: "ERROR", sql_state, message}])])["health.errors"].status, status);
  const top = table("server_log.top_errors", [{severity_worst: "FATAL", message_sample: "could not receive data from client: Connection reset by peer", occurrences: 50}]);
  assert.equal(evaluate([top])["network.clients.disconnects"].status, "crit");
});

test("overlapping deadlock sources use the same rate in locks and errors", () => {
  for (const [count, expected] of [[1, "ok"], [600, "crit"]]) {
    const nodes = evaluate([
      table("server_log.deadlock_events", [{repeat_count: count}]),
      table("server_log.error_chronology", [{severity: "ERROR", sql_state: "40P01", message: "deadlock detected", repeat_count: count}]),
      table("server_log.top_errors", [{severity_worst: "ERROR", sql_state: "40P01", message_sample: "deadlock detected", occurrences: count}])
    ]);
    assert.equal(nodes["health.errors"].score, nodes["health.locks"].score);
    assert.equal(nodes.database_health.status, expected);
  }
});

test("deadlock rate includes events omitted from the table and supports older reports", () => {
  const capped = evaluate([table("server_log.deadlock_events", [{repeat_count: 1}], {
    matched_event_count: 600, displayed_event_count: 1, omitted_event_count: 599
  })])["health.locks"];
  const full = evaluate([table("server_log.deadlock_events", [{repeat_count: 600}])])["health.locks"];
  assert.equal(capped.score, full.score);
  assert.ok(capped.reasons.some(reason => reason.includes("600 deadlock(s)")));
});

test("table and statement I/O use server block size and keep unknown sizes in blocks", () => {
  for (const [id, column] of [["snapshot_delta_workload.table_io_delta", "total_blks_read_per_sec"],
    ["snapshot_delta_workload.sql_io_delta", "shared_read_blks_per_sec"]]) {
    const reads = table(id, [{schemaname: "public", relname: "t", query_id: 1, [column]: 10000}]);
    for (const [size, label, expected] of [[32768, "312.5 MiB/s", 0.6], [8192, "78.1 MiB/s", null], [null, "10.0 k blocks/s", null]]) {
      const settings = size ? [table("overview.pg_settings", [{name: "block_size", setting: String(size)}])] : [];
      const node = evaluate([reads, disk(), ...settings])["disk.read.queries"];
      assert.ok(node.reasons.some(reason => reason.includes(label)), node.reasons.join(" "));
      if (expected !== null) assert.equal(node.ownScore, expected);
      if (size === 8192) assert.ok(node.ownScore > 0 && node.ownScore < 0.3);
      if (size === null) assert.equal(node.ownScore, null);
    }
  }
});

test("SyncRep verdict respects recovery, commit requirements and source risk in both branches", () => {
  for (const [extra, expected] of [
    [{in_recovery: true, commit_waits_for_standby: true, risk_level: "ok"}, "ok"],
    [{in_recovery: false, commit_waits_for_standby: true, risk_level: "high"}, "crit"],
    [{in_recovery: false, commit_waits_for_standby: false, risk_level: "medium"}, "warn"],
    [{in_recovery: false, commit_waits_for_standby: true, risk_level: "medium"}, "warn"],
    [{in_recovery: false, commit_waits_for_standby: false, syncrep_waiting_sessions: 2}, "crit"]
  ]) {
    const nodes = evaluate([table("replication.synchronous_replication_status", [{quorum_satisfied: false, syncrep_waiting_sessions: 0, ...extra}])]);
    assert.equal(nodes["network.replication.sync"].status, expected);
    assert.equal(nodes["health.replication"].status, expected);
  }
});

test("pg_stat_io byte shares use native byte counters or each row's op_bytes", () => {
  for (const delta of [false, true]) {
    const id = delta ? "snapshot_delta_workload.postgresql_io_delta" : "wal_io_checkpoints.pg_stat_io";
    const count = delta ? "reads_delta" : "reads", bytes = delta ? "read_bytes_delta" : "read_bytes";
    for (const native of [false, true]) {
      const rows = [
        {backend_type: "autovacuum worker", [count]: 100, op_bytes: 32768, ...(native ? {[bytes]: 3276800} : {})},
        {backend_type: "client backend", [count]: 100, op_bytes: 8192, ...(native ? {[bytes]: 819200} : {})}
      ];
      if (native) for (const row of rows) row.op_bytes = 1; // bytes take precedence over operation estimates
      const nodes = evaluate([table(id, rows), disk()]);
      const shares = Object.values(nodes).filter(node => node.facts["Autovacuum read share"] !== undefined);
      assert.ok(shares.length >= 2);
      for (const node of shares) assert.equal(node.facts["Autovacuum read share"], "80 %");
      if (!native) {
        delete rows[1].op_bytes;
        const unknown = evaluate([table(id, rows), disk()]);
        assert.ok(Object.values(unknown).every(node => node.facts["Autovacuum read share"] === undefined),
          "one unknown byte count prevents a fabricated partial denominator");
      }
    }
  }
});

test("checkpoint wall times use the collected server offset, not the browser time zone", () => {
  const previousTZ = process.env.TZ;
  try {
    for (const zone of ["UTC", "Europe/Moscow", "America/New_York"]) {
      process.env.TZ = zone;
      const runtime = coverage(), log = checkpointLog();
      runtime.log_collection.coverage.covered_from = "2026-09-05 03:00:00";
      runtime.log_collection.coverage.covered_to = "2026-09-05 04:00:00";
      Object.assign(log.result.rows[0], {log_time: "2026-09-05 03:00:00", last_time: "2026-09-05 03:01:00"});
      log.result.rows[1].log_time = "2026-09-05 04:00:00";
      log.result.log_utc_offset_seconds = 10800;
      assert.equal(evaluate([checkpointChart(), log, disk()], runtime)["disk.write.checkpoints"].status, "ok", zone);
      delete log.result.log_utc_offset_seconds;
      assert.equal(evaluate([checkpointChart(), log, disk()], runtime)["disk.write.checkpoints"].status, "crit", "unknown log zone cannot replace counts");
    }
  } finally {
    if (previousTZ === undefined) delete process.env.TZ;
    else process.env.TZ = previousTZ;
  }
});
