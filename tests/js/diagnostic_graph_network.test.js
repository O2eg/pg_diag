"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const G = require("../../src/pg_diag/render/graph/pg-diag-graph.js");
const definition = require("../../src/pg_diag/render/graph/graph.json");

function table(id, rows) {
  const names = [...new Set(rows.flatMap(row => Object.keys(row)))];
  return {item_id: id, collection_status: rows.length ? "ok" : "empty", result: {
    kind: "table", columns: names.map(name => ({name, encoding: "json_value"})), rows, row_count: rows.length
  }};
}
function chart(id, series, extra) {
  return {item_id: id, collection_status: "ok", result: {kind: "chart",
    series: Object.entries(series).map(([name, values]) => ({name, points: values.map((value, n) => ({t: `2026-09-05T00:00:0${n}Z`, value}))})), ...extra
  }};
}
function evaluate(items, runtime) {
  return G.evaluate({items: Object.fromEntries(items.map(i => [i.item_id, i])), runtime: {
    mode: "snapshots", collection_mode: "local", duration_seconds: 60, ...runtime
  }}, definition).nodes;
}

test("Network has six symptom groups and is independent of CPU pressure", () => {
  const nodes = evaluate([chart("snapshot_charts_os.os_network_errors", {"rx errors (eth0)": [0, 12, 0]}),
    chart("snapshot_charts_os.os_cpu_utilization", {system: [0, 0, 0], user: [0, 0, 0]})]);
  assert.equal(nodes.network.children.length, 6);
  assert.equal(nodes.network.status, "crit");
  assert.equal(nodes["network.interfaces.errors"].status, "crit");
  assert.equal(nodes.cpu.status, "ok");
});

test("interface errors and drops preserve peaks: any error warns, drops warn from a material rate", () => {
  for (const [suffix, peak, expected] of [["errors", 0, "ok"], ["errors", 0.1, "warn"], ["errors", 10, "crit"], ["drops", 1, "ok"], ["drops", 20, "warn"], ["drops", 100, "crit"]]) {
    const nodes = evaluate([chart("snapshot_charts_os.os_network_" + suffix, {["rx " + suffix + " (eth0)"]: [0, peak, 0]})]);
    assert.equal(nodes["network.interfaces." + suffix].status, expected);
  }
});

test("old empty, all-null, rollback and one-point rate charts are not measured zero", () => {
  for (const series of [{}, {rx: [null, null]}, {rx: [-1, -2]}, {rx: [1]}]) {
    const nodes = evaluate([chart("snapshot_charts_os.os_network_errors", series)]);
    assert.equal(nodes["network.interfaces.errors"].status, "no_data");
  }
  const node = evaluate([], {mode: "one-shot", collection_mode: "remote-db-only"})["network.interfaces.errors"];
  assert.equal(node.status, "no_data");
  assert.ok(node.hints.some(h => /snapshots/.test(h)));
  assert.ok(node.hints.some(h => /remote-db-only/.test(h)));
});

test("hidden-zero metadata proves a measured zero only with sufficient complete samples", () => {
  for (const [sample_count, missing_count, expected] of [[3, 0, "ok"], [1, 0, "no_data"], [3, 1, "no_data"]]) {
    const nodes = evaluate([chart("snapshot_charts_os.os_network_errors", {}, {
      zero_series: [{name: "rx errors (eth0)", sample_count, missing_count}]
    })]);
    assert.equal(nodes["network.interfaces.errors"].status, expected);
  }
});

test("bandwidth requires exact interface current speed, not hardware capacity", () => {
  const rx = chart("snapshot_charts_os.os_network_receive", {"rx (eth0)": [120e6, 120e6]});
  for (const row of [{logicalname: "eth0", capacity: 1e9}, {logicalname: "eth1", configuration: {speed: "1Gbit/s"}}]) {
    const nodes = evaluate([rx, table("os.lshw_network", [row])]);
    assert.equal(nodes["network.traffic.receive"].status, "no_data");
    assert.ok(Object.keys(nodes["network.traffic.receive"].facts).length);
  }
  const nodes = evaluate([rx, table("os.lshw_network", [{logicalname: ["eth0"], configuration: {speed: "1Gbit/s"}}])]);
  assert.equal(nodes["network.traffic.receive"].status, "crit");
});

test("failed inventory and receiver payloads are not usable network evidence", () => {
  const nic = table("os.lshw_network", [{logicalname: "eth0", configuration: {speed: "1Gbit/s"}}]);
  nic.collection_status = "error";
  const receiver = table("replication.wal_receiver", [{status: "stopped", receive_lag_bytes: 1e10}]);
  receiver.collection_status = "unsupported";
  const nodes = evaluate([nic, receiver,
    chart("snapshot_charts_os.os_network_receive", {"rx (eth0)": [120e6, 120e6]}),
    chart("snapshot_charts_db.standby_wal_rate", {received: [1, 1]})]);
  assert.equal(nodes["network.traffic.receive"].status, "no_data");
  assert.equal(nodes["network.replication.receive"].status, "no_data");
});

test("full-duplex directions and overlapping virtual interfaces are not summed", () => {
  const nodes = evaluate([
    chart("snapshot_charts_os.os_network_receive", {"rx (eth0)": [60e6, 60e6], "rx (bridge0)": [60e6, 60e6]}),
    chart("snapshot_charts_os.os_network_transmit", {"tx (eth0)": [60e6, 60e6]}),
    table("os.lshw_network", [{logicalname: "eth0", configuration: {speed: "1Gbit/s"}}])
  ]);
  assert.equal(nodes["network.traffic.receive"].status, "ok");
  assert.equal(nodes["network.traffic.transmit"].status, "ok");
});

test("high packet rate alone is not a critical bandwidth verdict", () => {
  const packets = chart("snapshot_charts_os.os_network_packets", {"rx packets (eth0)": [1e6, 1e6]});
  assert.equal(evaluate([packets])["network.traffic.packets"].status, "no_data");
  const cpu = chart("snapshot_charts_os.os_cpu_utilization", {system: [1, 1]});
  assert.equal(evaluate([packets, cpu])["network.traffic.packets"].status, "ok");
});

test("ClientRead is informational; ClientWrite is backpressure, not isolated network failure", () => {
  let nodes = evaluate([table("activity_locks.wait_events", [{wait_event: "ClientRead", sessions: 100}])]);
  assert.equal(nodes["network.clients.read"].score, null);
  assert.equal(nodes["network.clients.write"].status, "ok");
  nodes = evaluate([table("activity_locks.wait_events", [{wait_event: "ClientWrite", sessions: 30}])]);
  assert.equal(nodes["network.clients.write"].status, "crit");
  assert.match(nodes["network.clients.write"].reasons.join(" "), /slow consumer/);
});

test("sampled ClientWrite is evidence independently of an empty final wait snapshot", () => {
  const nodes = evaluate([table("activity_locks.wait_events", []),
    chart("activity_locks.wait_event_sample_profile", {"Client:ClientWrite": [25, 25]})]);
  assert.equal(nodes["network.clients.write"].status, "crit");
});

test("timeouts, administrator kills and message fragments in SQL do not score transport", () => {
  const rows = [
    {sql_state: "57014", message: "canceling statement due to statement timeout", occurrences: 100},
    {sql_state: "57P01", message: "terminating connection due to administrator command", occurrences: 100},
    {sql_state: "42601", message: 'syntax error at or near "could not receive data from client"', occurrences: 100}
  ];
  const nodes = evaluate([table("server_log.error_chronology", rows),
    table("snapshot_delta_workload.database_session_outcomes_delta", [{sessions_killed_delta: 100, sessions_fatal_delta: 100, sessions_abandoned_delta: 0}])]);
  assert.equal(nodes["network.clients.disconnects"].status, "ok");
});

test("connection failure sources overlap and abandoned-session window stays separate", () => {
  const rows = [{sql_state: "08006", message: "localized connection failure", occurrences: 7}];
  const nodes = evaluate([table("server_log.error_chronology", rows), table("server_log.top_errors", rows),
    table("snapshot_delta_workload.database_session_outcomes_delta", [{sessions_abandoned_delta: 2}])]);
  const node = nodes["network.clients.disconnects"];
  assert.equal(node.status, "warn");
  assert.equal(node.facts["Shown transport failures (overlapping sources)"], "7");
  assert.equal(node.facts["Abandoned sessions in snapshot window"], "2");
});

test("replay or flush backlog alone is not network send pressure", () => {
  const nodes = evaluate([
    table("replication.physical_replication", [{current_to_sent_lag_bytes: 0, sent_to_write_lag_bytes: 0, current_to_replay_lag_bytes: 1e10}]),
    chart("snapshot_charts_db.replication_sender_lag_bytes", {"replay lag (standby)": [1e10, 1e10], "flush lag (standby)": [1e10, 1e10]}),
    table("replication.wal_receiver", [{status: "streaming", receive_lag_bytes: 0, seconds_since_last_message: 9999}])
  ]);
  assert.equal(nodes["network.replication.send"].status, "ok");
  assert.equal(nodes["network.replication.receive"].status, "ok");
  assert.equal(nodes["health.replication"].status, "crit");
});

test("send backlog and missing synchronous quorum reach the Network root", () => {
  const send = evaluate([chart("snapshot_charts_db.replication_sender_lag_bytes", {"sent lag (standby)": [2e9, 2e9]})]);
  assert.equal(send["network.replication.send"].status, "crit");
  const sync = evaluate([table("replication.synchronous_replication_status", [{quorum_satisfied: false, syncrep_waiting_sessions: 3}])]);
  assert.equal(sync.network.status, "crit");
});

test("streaming disconnect node ignores archive failures and recovery conflicts", () => {
  const rows = [{event_type: "archive_failure", occurrences: 500}, {event_type: "recovery_conflict", occurrences: 500}];
  assert.equal(evaluate([table("server_log.replication_events", rows)])["network.replication.failures"].status, "ok");
  rows.push({event_type: "walreceiver_disconnect", occurrences: 1});
  assert.equal(evaluate([table("server_log.replication_events", rows)])["network.replication.failures"].status, "warn");
});

test("reconnects use window deltas, not existing connections or statement call totals", () => {
  const nodes = evaluate([table("snapshot_delta_workload.database_session_outcomes_delta", [{sessions_delta: 3600}]),
    table("sql_workload.top_sql_by_calls", [{calls: 1e10, mean_exec_time_ms: 0.1}])]);
  assert.equal(nodes["network.clients.churn"].status, "crit");
  assert.equal(nodes["network.clients.roundtrips"].score, null);
  assert.equal(nodes["network.clients.churn"].facts["New sessions per second"], "60.00");
});
