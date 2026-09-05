/* Independent assessments for report-item directions. No DOM dependencies. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(require("./pg-diag-graph-data.js"), require("./pg-diag-graph-rules.js"));
  } else {
    root.PgDiagGraphGroups = factory(root.PgDiagGraphData, root.PgDiagGraphRules);
  }
})(typeof self !== "undefined" ? self : this, function (Data, Rules) {
  "use strict";
  const {toNumber, isFiniteNumber, maxScore, statusOf, fmtBytes, fmtNum, fmtPct,
    seriesStats, sumSeries, sumBy, maxBy, hasColumn, observedZeros} = Data;
  const T = Rules.THRESHOLDS;
  const collected = (ctx, id) => ["present", "empty"].includes(ctx.presence(id));
  const numeric = value => { const n = toNumber(value); return n !== null && n >= 0 ? n : null; };
  const format = (value, unit) => unit === "B/s" ? fmtBytes(value) + "/s" : unit === "B" ? fmtBytes(value) : fmtNum(value, 2) + (unit ? " " + unit : "");

  // These are actual color boundaries, not the endpoints of a continuous score ramp.
  function metric(ctx, label, value, pair, unit, id) {
    if (!isFiniteNumber(value)) return null;
    if (value < 0) { ctx.missing(label + " is negative; a reset or invalid interval cannot establish a healthy measurement."); return null; }
    const reverse = pair[0] > pair[1];
    const reached = threshold => reverse ? value <= threshold : value >= threshold;
    const score = reached(pair[1]) ? 1 : reached(pair[0]) ? 0.5 : 0;
    ctx.fact(label, format(value, unit));
    ctx.reason(label + ": " + format(value, unit) + "; warning " + (reverse ? "≤ " : "≥ ") + format(pair[0], unit) + ", critical " + (reverse ? "≤ " : "≥ ") + format(pair[1], unit), id);
    return score;
  }
  function totalStats(ctx, id, pattern) {
    const series = ctx.series(id).filter(s => !pattern || pattern.test(s.name));
    if (series.some(s => s.values.some(v => isFiniteNumber(v) && v < 0))) ctx.missing(ctx.title(id) + ": negative samples indicate an invalid interval or counter reset.");
    const valid = series.map(s => ({...s, values: s.values.map(v => v < 0 ? NaN : v)}));
    if (valid.length) return seriesStats(sumSeries(valid, {missing: "strict"}), ctx.minimumSamples(id));
    const zeros = observedZeros(ctx, id).filter(s => !pattern || pattern.test(s.name));
    return zeros.length ? {mean: 0, p95: 0, max: 0, sum: 0} : null;
  }
  function chartMetric(ctx, id, label, pair, unit, pattern) {
    const stats = totalStats(ctx, id, pattern);
    if (!stats) return null;
    ctx.fact(label + " mean", format(stats.mean, unit));
    return metric(ctx, label + " p95", stats.p95, pair, unit, id);
  }
  function rowMetric(ctx, id, column, label, pair, unit) {
    return metric(ctx, label, maxBy(ctx.rows(id), column).value, pair, unit, id);
  }
  function countCheck(ctx, id, label, columns, score = 0.5) {
    const rows = ctx.rows(id);
    const values = columns.map(c => sumBy(rows, c)).filter(isFiniteNumber);
    if (!values.length) {
      if (ctx.presence(id) !== "empty") return null;
      ctx.reason(label + ": no matching events collected", id);
      return 0;
    }
    const count = values.reduce((a, b) => a + b, 0);
    if (count < 0) return null;
    ctx.fact(label, String(count));
    ctx.reason(label + ": " + count + "; " + (score >= 0.67 ? "critical" : "warning") + " when greater than zero", id);
    return count > 0 ? score : 0;
  }
  function legacy(ctx, name, explanation) {
    const score = Rules.evaluators[name](ctx);
    if (explanation) ctx.reason(explanation);
    return score;
  }
  function findings(ctx) {
    let score = null;
    const levels = {critical: 1, high: 1, medium: 0.5, moderate: 0.5, low: 0.5, info: 0, ok: 0, none: 0};
    for (const b of ctx.node.bindings) {
      const item = ctx.item(b.id);
      if (!item) continue;
      const rows = ctx.rows(b.id);
      if (hasColumn(item, "risk_level")) {
        if (ctx.presence(b.id) === "empty") {
          ctx.reason(ctx.title(b.id) + ": no risk findings returned", b.id);
          score = maxScore(score, 0);
        }
        for (const row of rows) {
          const level = String(row.risk_level || "").trim().toLowerCase();
          if (!(level in levels)) {
            ctx.missing(ctx.title(b.id) + ": " + (level === "unknown" ? row.risk_reason || "The report cannot judge this configuration without an approved baseline." : "Unrecognized risk level: " + (level || "missing")));
            continue;
          }
          score = maxScore(score, levels[level]);
          if (levels[level] > 0) ctx.reason(ctx.title(b.id) + ": " + level + (row.risk_reason ? " — " + Data.truncate(row.risk_reason, 220) : ""), b.id);
        }
        if (rows.length) ctx.fact(ctx.title(b.id) + " assessed rows", String(rows.length));
      } else if (isFiniteNumber(b.weight) && collected(ctx, b.id)) {
        // An explicit binding weight marks a findings-only query, never an inventory.
        const severity = b.weight >= 0.67 ? 1 : 0.5;
        score = maxScore(score, rows.length ? severity : 0);
        ctx.reason(ctx.title(b.id) + ": " + rows.length + " findings; " + (severity === 1 ? "critical" : "warning") + " if any", b.id);
      }
    }
    if (score !== null) ctx.reason("Reported risk levels: low/medium → Warning; high/critical → Critical; ok/info → OK.");
    return score;
  }

  const evaluators = {
    reference(ctx) {
      for (const b of ctx.node.bindings) {
        for (const series of ctx.series(b.id).slice(0, 4)) {
          const stats = seriesStats(series.values, ctx.minimumSamples(b.id));
          if (stats) ctx.fact(ctx.title(b.id) + " / " + series.name + " mean / p95", fmtNum(stats.mean, 2) + " / " + fmtNum(stats.p95, 2) + (series.unit ? " " + series.unit : " (source units)"));
        }
        if (ctx.rows(b.id).length) ctx.fact(ctx.title(b.id), ctx.rows(b.id).length + " rows collected");
      }
      ctx.missing(ctx.group.unassessed_reason || "These sources describe activity or inventory; they do not provide a health criterion. Data presence alone cannot establish OK.");
      return null;
    },
    findings,
    wal_generation(ctx) {
      const chartId = "snapshot_charts_db.wal_growth_rate", deltaId = "snapshot_delta_workload.wal_activity_delta";
      let rate = chartMetric(ctx, chartId, "WAL generation", T.walBytesPerSec, "B/s");
      if (rate === null) rate = rowMetric(ctx, deltaId, "wal_bytes_per_sec", "WAL generation in window", T.walBytesPerSec, "B/s");
      let score = rate;
      const delta = ctx.rows(deltaId);
      const id = delta.length ? deltaId : "wal_io_checkpoints.wal_statistics";
      const row = (delta.length ? delta : ctx.rows(id))[0];
      if (row) {
        const suffix = delta.length ? "_delta" : "";
        const records = numeric(row["wal_records" + suffix]), fpi = numeric(row["wal_fpi" + suffix]);
        if (records > 0 && fpi !== null) score = maxScore(score, metric(ctx, "Full-page images per record" + (delta.length ? " in window" : " since reset"), fpi / records, T.fpiShare, "", id));
        if (delta.length && numeric(row.wal_buffers_full_delta) !== null) score = maxScore(score, countCheck(ctx, deltaId, "WAL buffer exhaustion events in window", ["wal_buffers_full_delta"]));
      }
      if (rate === null) ctx.missing("WAL generation rate is unavailable: collect at least two valid WAL samples or a valid WAL delta window. An LSN or cumulative byte count does not establish a rate.");
      ctx.reason("WAL rate and full-page-image thresholds are triage heuristics. High generation is not by itself proof of disk saturation; check device latency and I/O waits.");
      return score;
    },
    wal_statements(ctx) {
      const id = "snapshot_delta_workload.sql_wal_delta";
      let score = rowMetric(ctx, id, "wal_bytes_per_sec", "Largest statement WAL rate", T.walBytesPerSec, "B/s");
      const total = maxBy(ctx.rows("sql_workload.top_sql_by_wal"), "wal_bytes");
      if (total.value !== null) ctx.fact("Largest cumulative statement WAL", fmtBytes(total.value));
      if (score === null) ctx.missing("Per-statement WAL bytes/s are unavailable. Cumulative WAL totals cannot establish a high generation rate.");
      ctx.reason("Compare the largest per-statement rate with the WAL generation thresholds; listed statements can cover different statistics windows.");
      return score;
    },
    durability(ctx) {
      let score = null;
      const id = "overview.durability_safety_settings";
      const seen = new Set();
      for (const row of ctx.rows(id)) {
        const name = String(row.setting_name), value = String(row.current_value).toLowerCase();
        if (!["fsync", "full_page_writes", "synchronous_commit"].includes(name)) continue;
        ctx.fact(name, value);
        const valid = name === "synchronous_commit" ? ["on", "off", "local", "remote_write", "remote_apply"] : ["on", "off"];
        if (!valid.includes(value)) { ctx.missing("Unrecognized value for " + name); continue; }
        seen.add(name);
        const severity = value === "off" ? (name === "synchronous_commit" ? 0.5 : 1) : 0;
        score = maxScore(score, severity);
        ctx.reason(name + " = " + value + "; " + (name === "synchronous_commit" ? "off warns about loss of recent commits after a crash" : "off is critical for crash durability"), id);
      }
      if (seen.size && seen.size < 3) ctx.missing("Durability assessment requires fsync, full_page_writes and synchronous_commit together.");
      return score;
    },
    connection_limits(ctx) {
      return rowMetric(ctx, "activity_locks.connection_pressure", "used_pct", "Connections used", T.connectionsUsedPct, "%");
    },
    sessions(ctx) {
      const score = rowMetric(ctx, "users_roles.session_usage", "limit_utilization_pct", "Highest role connection-limit usage", T.connectionsUsedPct, "%");
      const risk = findings(ctx);
      if (score === null && risk === null) ctx.missing("Session counts without a finite connection limit do not establish capacity pressure.");
      return maxScore(score, risk);
    },
    connection_outcomes(ctx) {
      const id = "server_log.system_incidents";
      const rows = ctx.rows(id).filter(r => r.incident_type === "too_many_connections");
      let score = collected(ctx, id) ? 0 : null;
      if (score !== null) {
        const count = rows.reduce((n, r) => n + (numeric(r.occurrences) ?? 1), 0);
        ctx.fact("Refused connections in log", count);
        ctx.reason(count + " refused connections; any refusal caused by exhausted slots is critical", id);
        if (count) score = 1;
      }
      const deltaId = "snapshot_delta_workload.database_session_outcomes_delta";
      for (const [col, label] of [["sessions_fatal_delta", "Fatal sessions"], ["sessions_killed_delta", "Killed sessions"], ["sessions_abandoned_delta", "Abandoned sessions"]]) {
        score = maxScore(score, metric(ctx, label + " in window", sumBy(ctx.rows(deltaId), col), T.sessionFailures, "", deltaId));
      }
      return score;
    },
    transactions(ctx) {
      if (ctx.node.bindings.every(b => ctx.presence(b.id) === "empty")) ctx.reason("No long or idle-in-transaction sessions returned by the collected checks.");
      return maxScore(
      rowMetric(ctx, "activity_locks.long_transactions", "xact_age_seconds", "Longest transaction", T.longTransactionSec, "s"),
      rowMetric(ctx, "activity_locks.idle_in_transaction", "idle_seconds", "Longest idle transaction", T.idleInTransactionSec, "s"),
      ctx.node.bindings.every(b => ctx.presence(b.id) === "empty") ? 0 : null
    ); },
    blocking(ctx) {
      const id = "activity_locks.lock_waits";
      const rows = ctx.rows(id);
      let score = null;
      if (collected(ctx, id) && (!rows.length || rows.some(r => numeric(r.blocked_ms) !== null))) {
        score = metric(ctx, "Blocked sessions", rows.length, T.blockedSessions, "", id);
        score = maxScore(score, rowMetric(ctx, id, "blocked_ms", "Longest lock wait", T.lockWaitMs, "ms"));
      }
      return maxScore(score, rowMetric(ctx, "activity_locks.blocking_lock_tree", "root_blocked_sessions", "Sessions held by the largest root blocker", T.blockedSessions, ""));
    },
    deadlocks(ctx) { return legacy(ctx, "locks", "Deadlocks are assessed by rate in the measured window; overlapping log/chart/delta observations are not added."); },
    lock_events(ctx) { return legacy(ctx, "locks", "Logged wait duration and timeout/cancellation events determine this direction's assessment."); },
    device(ctx) {
      let score = null;
      for (const s of ctx.series("snapshot_charts_os.os_disk_latency").filter(s => /^await/.test(s.name))) {
        const device = (/\(([^)]+)\)/.exec(s.name) || [null, s.name])[1];
        const media = ctx.facts.mediaFor(device), stats = seriesStats(s.values, 2);
        if (stats) score = maxScore(score, metric(ctx, device + " (" + media + ") await p95", stats.p95, T.diskLatencyMs[media] || T.diskLatencyMs.unknown, "ms", "snapshot_charts_os.os_disk_latency"));
      }
      for (const s of ctx.series("snapshot_charts_os.os_disk_utilization")) {
        const device = (/\(([^)]+)\)/.exec(s.name) || [null, s.name])[1], stats = seriesStats(s.values, 2);
        if (!stats) continue;
        ctx.fact(device + " utilization p95", fmtPct(stats.p95));
        if (ctx.facts.mediaFor(device) === "hdd") score = maxScore(score, metric(ctx, device + " HDD utilization p95", stats.p95, T.diskUtilPct, "%", "snapshot_charts_os.os_disk_utilization"));
      }
      ctx.reason("Latency thresholds depend on storage type. SSD/NVMe utilization without latency cannot establish saturation.");
      return score;
    },
    memory(ctx) { return legacy(ctx, "memory_available", "Memory assessment uses available capacity and explicit OOM evidence from this direction's sources."); },
    crashes(ctx) { return legacy(ctx, "crashes", "Only crash/corruption evidence is scored; routine startup, shutdown and unrelated connection incidents are not crashes."); },
    vacuum(ctx) { return legacy(ctx, "vacuum_lag", "Overdue vacuum requires accumulated dead tuples; running or insert-triggered vacuum alone is not lag."); },
    bloat(ctx) { return legacy(ctx, "bloat", "Bloat estimates are assessed only for objects with at least " + fmtBytes(T.bloatMinWastedBytes) + " estimated waste."); },
    configuration(ctx) {
      let score = maxScore(legacy(ctx, "configuration"), evaluators.durability(ctx));
      const id = "cluster_inventory.pending_restart_settings", count = ctx.rows(id).length;
      if (count) { score = maxScore(score, 0.5); ctx.reason(count + " settings require restart (warning)", id); }
      return score;
    },
    statements(ctx) { return legacy(ctx, "heavy_queries", "Execution duration is not CPU time. CPU use requires the per-statement CPU delta; time concentration alone can only warn."); },
    system_cpu(ctx) { return chartMetric(ctx, "snapshot_charts_os.os_cpu_utilization", "System CPU", T.cpuSystemPct, "%", /^(system|irq|softirq)$/i); },
    functions(ctx) {
      const id = "snapshot_delta_workload.function_time_delta";
      ctx.reason("Function elapsed time includes waits and nested calls; it is not a CPU measurement.");
      return rowMetric(ctx, id, "total_time_ms_per_sec", "Largest function elapsed time rate", [1000, 4000], "ms/s");
    },
    plans(ctx) {
      let score = rowMetric(ctx, "server_log.query_resource_events", "max_duration_ms", "Longest logged statement", T.meanExecMs, "ms");
      const durations = ctx.series("server_log.auto_explain_plans").map(s => seriesStats(s.values, 1)).filter(Boolean);
      if (durations.length) score = maxScore(score, metric(ctx, "Longest auto_explain plan duration", Math.max(...durations.map(s => s.max)), T.meanExecMs, "ms", "server_log.auto_explain_plans"));
      ctx.reason("Only statements meeting logging thresholds are represented; logged duration includes waits and does not prove CPU pressure.");
      return score;
    },
    statement_kernel(ctx) {
      const id = "snapshot_delta_workload.sql_kernel_cpu_delta";
      return rowMetric(ctx, id, "system_cpu_pct", "Largest statement system CPU share", T.kernelShare.map(n => n * 100), "%");
    },
    index_activity(ctx) {
      const id = "object_workload.index_workload";
      let score = ctx.presence(id) === "empty" ? 0 : null, count = 0;
      for (const row of ctx.rows(id)) {
        const read = numeric(row.idx_tup_read), fetch = numeric(row.idx_tup_fetch);
        if (read === null || fetch === null) continue;
        if (read > 100000 && fetch === 0) { ctx.missing("Index " + row.indexrelname + " has no heap fetches; index-only scans must be distinguished from wasted reads using its plan."); continue; }
        score = maxScore(score, 0);
        if (read > 100000 && read / fetch > T.idxScale) {
          score = 0.5; count++;
          ctx.reason("Index " + row.indexrelname + ": " + fmtNum(read / fetch, 0) + " entries per heap fetch; review when above " + T.idxScale + " with over 100,000 entries read", id);
        }
      }
      ctx.fact("Indexes requiring plan review", count);
      ctx.reason("Read amplification is a warning for plan review, not proof of a bad index. Index-only scans can explain a high ratio; this rule does not assign Critical.");
      return score;
    },
    temp_statements(ctx) { return rowMetric(ctx, "snapshot_delta_workload.sql_temp_io_delta", "temp_io_bytes_per_sec", "Largest statement temporary I/O", T.tempBytesPerSec, "B/s"); },
    temp_database(ctx) { return chartMetric(ctx, "snapshot_charts_db.database_temp_bytes_rate", "Temporary file generation", T.tempBytesPerSec, "B/s"); },
    checkpoint_activity(ctx) { return legacy(ctx, "checkpoints", "Requested checkpoint share is checked in the observed window; explicit/manual checkpoints in logs are excluded from WAL-pressure evidence."); },
    checkpoint_timing(ctx) {
      const id = "snapshot_charts_db.checkpoint_write_sync_time_delta";
      const stats = totalStats(ctx, id, /^sync$/i);
      ctx.reason("Sync time is summed per sampled interval and may include multiple checkpoints; paced write time is not a latency alarm.");
      if (stats) ctx.fact("Checkpoint sync time per interval p95", format(stats.p95, "ms"));
      const deltaId = "snapshot_delta_workload.checkpointer_delta", row = ctx.rows(deltaId)[0];
      if (row) {
        const done = numeric(row.checkpoints_done_delta), sync = numeric(row.sync_time_ms_delta);
        if (done > 0 && sync !== null) return metric(ctx, "Mean sync time per completed checkpoint in window", sync / done / 1000, T.checkpointSyncSec, "s", deltaId);
        if (done === 0 && sync === 0) { ctx.reason("No checkpoint completed and no sync time accumulated in the measured window.", deltaId); return 0; }
      }
      ctx.missing("The sync-time chart alone has no per-checkpoint denominator. Collect a valid checkpointer delta or inspect individual sync durations in checkpoint logs.");
      return null;
    },
    dml(ctx) {
      ctx.reason("DML volume is a triage heuristic, not proof of excessive resource use.");
      return rowMetric(ctx, "snapshot_delta_workload.table_dml_delta", "total_dml_per_sec", "Highest table DML rate", T.dmlRowsPerSec, "rows/s");
    },
    table_churn(ctx) {
      let score = null;
      const id = "object_workload.table_workload";
      let worst = null;
      for (const row of ctx.rows(id)) {
        const live = numeric(row.n_live_tup), dead = numeric(row.n_dead_tup);
        if (live === null || dead === null) continue;
        if (live + dead <= T.deadTupleMinRows) { score = maxScore(score, 0); continue; }
        const pct = 100 * dead / (live + dead);
        if (!worst || pct > worst.pct) worst = {row, pct};
      }
      if (worst) score = maxScore(score, metric(ctx, (worst.row.schemaname || "") + "." + (worst.row.relname || "table") + " dead tuples", worst.pct, T.deadTuplePct, "%", id));
      ctx.reason("Dead-tuple ratios are checked only above " + T.deadTupleMinRows + " live+dead tuples.");
      return score;
    },
    disk_space(ctx) { return legacy(ctx, "disk_space", "Filesystem free space is assessed against capacity; relation sizes alone do not establish exhaustion."); },
    storage_incidents(ctx) {
      const score = legacy(ctx, "disk_space");
      if (score === null && collected(ctx, "server_log.system_incidents")) {
        ctx.reason("No disk-full, read-only-filesystem or storage I/O failure found in the collected incident log.", "server_log.system_incidents");
        return 0;
      }
      return score;
    },
    disk_retention(ctx) { return maxScore(legacy(ctx, "disk_space"), legacy(ctx, "archiving")); },
    replication_senders(ctx) {
      const id = "replication.physical_replication";
      let score = ctx.presence(id) === "empty" ? 0 : null;
      if (score === 0) ctx.reason("No connected physical standby returned by the sender check.", id);
      for (const row of ctx.rows(id)) {
        const name = row.application_name || row.client_addr || "Standby";
        const bytes = numeric(row.current_to_replay_lag_bytes), seconds = numeric(row.replay_lag_seconds);
        if (bytes !== null) score = maxScore(score, metric(ctx, name + " replay lag", bytes, T.replayLagBytes, "B", id));
        if (seconds !== null) score = maxScore(score, metric(ctx, name + " replay delay", seconds, T.replayLagSec, "s", id));
        if (row.state) {
          ctx.fact(name + " state", row.state);
          if (row.state !== "streaming") { score = maxScore(score, 0.5); ctx.reason(name + " state is " + row.state + "; not yet streaming (warning)", id); }
        }
        if (!row.state || bytes === null && seconds === null) ctx.missing(name + ": sender state and a valid lag measurement are required.");
      }
      for (const s of ctx.series("snapshot_charts_db.replication_sender_lag_bytes").filter(s => /^replay(?:\s|$)/.test(s.name))) {
        const stats = seriesStats(s.values, 2);
        if (stats) score = maxScore(score, metric(ctx, s.name + " lag p95", stats.p95, T.replayLagBytes, "B", "snapshot_charts_db.replication_sender_lag_bytes"));
      }
      return score;
    },
    network_senders(ctx) { return legacy(ctx, "network_wal_send"); },
    replication_replay(ctx) {
      const state = ctx.rows("replication.standby_recovery_state");
      if (state.length && state[0].in_recovery === false && !ctx.rows("replication.wal_receiver").length) {
        ctx.reason("This server is a primary; WAL receive/replay is not applicable here.", "replication.standby_recovery_state");
        return 0;
      }
      if (!state.some(r => typeof r.in_recovery === "boolean") && !ctx.rows("replication.wal_receiver").some(r => r.status) && !ctx.series("snapshot_charts_db.standby_replay_lag_bytes").length) {
        ctx.missing("Receiver state and server recovery role are unavailable; an empty receiver list alone cannot distinguish a primary from a disconnected standby.");
        return null;
      }
      return legacy(ctx, "replication", "Replay delay requires unapplied WAL in matching samples.");
    },
    replication_slots(ctx) {
      const id = "replication.replication_slots";
      let score = ctx.presence(id) === "empty" ? 0 : null;
      if (score === 0) ctx.reason("No replication slots configured in the collected slot inventory.", id);
      for (const row of ctx.rows(id)) {
        if (["lost", "unreserved"].includes(row.wal_status)) {
          score = maxScore(score, row.wal_status === "lost" ? 1 : 0.5);
          ctx.reason("Slot " + row.slot_name + ": WAL status " + row.wal_status + (row.wal_status === "lost" ? " (critical: required WAL is no longer available)" : " (warning: required WAL is at risk of removal)"), id);
        } else if (["reserved", "extended"].includes(row.wal_status)) {
          score = maxScore(score, 0); ctx.fact("Slot " + row.slot_name + " WAL status", row.wal_status);
        }
        if (row.active === false) score = maxScore(score, metric(ctx, "Inactive slot " + row.slot_name + " retained WAL", numeric(row.retained_wal_bytes), T.retainedWalBytes, "B", id));
      }
      return maxScore(score, evaluators.replication_capacity(ctx), findings(ctx));
    },
    replication_sync(ctx) { return legacy(ctx, "network_sync"); },
    replication_capacity(ctx) { return rowMetric(ctx, "replication.replication_capacity", "utilization_pct", "Highest replication resource usage", T.capacityPct, "%"); },
    replication_logical(ctx) {
      let score = countCheck(ctx, "snapshot_delta_workload.subscription_errors_conflicts_delta", "Logical replication errors/conflicts in window", ["apply_error_count_delta", "sync_error_count_delta", "conflict_count_delta"]);
      const id = "replication.subscription_workers";
      for (const row of ctx.rows(id)) {
        if (row.subenabled === true && typeof row.worker_running === "boolean") {
          const failed = !row.worker_running;
          score = maxScore(score, failed ? 0.5 : 0);
          ctx.reason("Subscription " + row.subname + ": enabled worker " + (failed ? "not running (warning)" : "running"), id);
        }
      }
      if (score === null) score = countCheck(ctx, id, "Cumulative logical replication errors since reset", ["apply_error_count", "sync_error_count", "conflict_count"]);
      return score;
    },
    recovery_conflicts(ctx) { return countCheck(ctx, "snapshot_delta_workload.standby_recovery_conflicts_delta", "Recovery conflicts in window", ["conflicts_total_delta"]); },
    replication_events(ctx) {
      const id = "server_log.replication_events";
      if (!collected(ctx, id)) return null;
      let score = 0;
      for (const row of ctx.rows(id)) {
        const severity = String(row.severity || "").toUpperCase();
        const level = ["PANIC", "FATAL", "ERROR"].includes(severity) ? 1 : severity === "WARNING" ? 0.5 : 0;
        score = maxScore(score, level);
        if (level) ctx.reason((row.event_type || "Replication event") + ": " + severity + ", " + (numeric(row.occurrences) ?? 1) + " occurrence(s); " + Data.truncate(row.message, 180), id);
      }
      ctx.reason("Logged WARNING events warn; ERROR/FATAL/PANIC events are critical. Informational replication messages are not failures.");
      return score;
    }
  };

  function evaluate(items, runtime, group, bindings, onRead) {
    const reasons = [], facts = {}, evidence = [], missing = [];
    const ids = new Set(bindings.map(b => b.id));
    const access = Data.createAccess(Object.fromEntries([...ids].map(id => [id, items[id]])), onRead);
    const ctx = {runtime, group, node: {bindings}, ...access,
      title: id => items[id] ? items[id].title || id : id,
      anyPresent: () => bindings.some(b => ctx.presence(b.id) === "present"),
      anyCollected: () => bindings.some(b => collected(ctx, b.id)),
      logWindowMinutes: () => Data.logWindowMinutes(runtime),
      reason(text, id) { if (text && !reasons.includes(text)) reasons.push(text); if (id && ids.has(id) && !evidence.includes(id)) evidence.push(id); },
      fact(name, value) { if (value !== null && value !== undefined) facts[name] = String(value); },
      missing(text) { if (!missing.includes(text)) missing.push(text); }
    };
    // Reused rules see only this direction's declared inputs, including their fallbacks.
    // A sibling's incident or a parent score cannot leak into this assessment.
    for (const [method, fallback] of Object.entries({item: null, presence: "absent", rows: [], series: [], text: "", minimumSamples: 2})) {
      ctx[method] = id => ids.has(id) ? access[method](id) : fallback;
    }
    ctx.facts = Data.makeFacts(ctx);
    let score = null, error = null;
    try {
      if (typeof evaluators[group.evaluator] !== "function") throw new Error("Unknown direction evaluator " + group.evaluator);
      score = evaluators[group.evaluator](ctx);
      if (!isFiniteNumber(score)) score = null;
    } catch (caught) { error = String(caught.message || caught); }
    const unavailable = bindings.filter(b => !collected(ctx, b.id));
    if (!ctx.anyCollected()) ctx.missing("No usable sources collected for this direction. " + unavailable.map(b => ctx.title(b.id) + ": " + ctx.presence(b.id)).join("; "));
    if (score === null && !missing.length) ctx.missing("Collected sources lack the measurements required by this direction's rule (valid numeric values, observation window or applicable objects).");
    if (missing.length && score !== null && statusOf(score) === "ok") score = null;
    if (score !== null) reasons.unshift(statusOf(score) === "ok" ? "No warning conditions found in the assessed measurements." : "This direction has its own findings; the color is based on the evidence below.");
    return {score, reasons, facts, evidence, error, hints: missing};
  }
  return {evaluate, evaluators};
});
