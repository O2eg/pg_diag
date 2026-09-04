/*
 * pg_diag diagnostic graph engine.
 *
 * Reads a report artifact (the JSON embedded in the HTML report) and a graph
 * definition (graph.json), evaluates every node from the raw item data, and
 * returns a plain object the renderer draws. No DOM access, no dependencies.
 * See DIAGNOSTIC_GRAPH_SPEC.md for the contract.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.PgDiagGraph = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const VERSION = "1.0.0";

  // Thresholds: [warn, crit]. Each one names the runbook rule it implements.
  const THRESHOLDS = {
    cpuBusyPct: [70, 95],            // 1.1: CPU work share (100 - idle - iowait - steal); steal is scored separately
    cpuLoadPerCore: [1.0, 2.0],      // 1.1: vmstat r / load average against cores
    cpuStealPct: [5, 20],            // 1.2: hypervisor steal
    cpuSystemPct: [10, 25],          // 3.6: %sy > 10-15 %
    cpuIowaitPct: [5, 20],          // Graph triage heuristic for 1.1's high %wa; confirm with device latency, not a saturation proof
    kernelShare: [0.3, 0.5],         // 3.6: kernel CPU share of PostgreSQL CPU
    backendCpuShare: [0.5, 0.9],     // 3: client backends' share of all cores
    autovacuumCpuShare: [0.25, 0.5], // 3.4: autovacuum workers' share of all cores
    walsenderCpuShare: [0.1, 0.3],   // 4.5: walsender share of all cores
    otherCpuPct: [20, 50],           // 3: non-PostgreSQL CPU percent of the host
    topStatementShare: [0.5, 0.9],   // 3.3: one statement's share of total time
    meanExecMs: [1000, 10000],       // 3.3: mean execution time of the slowest statement
    seqShare: [0.3, 0.8],            // 3.1: seq tuple share on tables > 10k rows
    seqTables: [3, 10],              // 3.1: tables where seq reads beat index fetches
    idxScale: 100,                   // 3.2: idx_tup_read / idx_tup_fetch limit
    idxScaleCount: [1, 5],           // 3.2: indexes above the limit
    tpsHigh: [5000, 20000],          // 3.6: > 10k light statements per second
    lwlockSessions: [5, 20],         // 5.5: sessions waiting on LWLock/Buffer/IPC
    lwlockSharePct: [20, 50],        // 5.5: wait-sampling share of LWLock
    connectionsMany: [500, 2000],    // 6: thousands of backends
    sessionRate: [5, 50],            // 6: reconnect storm, sessions per second
    packetsPerSec: [50000, 200000],  // 3.6: packet rate that costs kernel time
    memAvailablePct: [10, 3],        // 4.3: available memory share (reversed)
    memUsedPct: [90, 97],            // 4.3: RAM used share
    swapUsedPct: [10, 50],           // 4.3: swap usage share
    workMemRatio: [0.5, 1.5],        // 4.3: work_mem x connections x 2 against RAM
    spillingStatements: [5, 20],     // 7 step 4: statements writing temp blocks
    sharedBuffersPct: [40, 70],      // 4.2 item 7: shared_buffers share of RAM
    sharedBuffersSmallPct: 10,       // 10: below 10 % is a warning
    cacheMissPct: [1, 10],           // 4.0: hit ratio < 99 % warn, < 90 % crit
    hugePagesMinBytes: 4 * 1024 ** 3, // 10: huge pages matter from 4 GB of shared memory
    pageTablesPct: [2, 5],           // 4.3: host page tables share of RAM
    diskLatencyMs: {nvme: [2, 10], ssd: [5, 20], hdd: [20, 50], unknown: [5, 20]}, // 1.1
    diskUtilPct: [90, 99],           // 1.1: only meaningful on HDD
    readShareWeight: 1,              // 4.0: parent pressure distributed by read/write share
    clientWriteShare: [0.1, 0.3],    // 4.2 item 4: backend writes share of relation writes
    requestedCheckpointShare: [0.3, 0.7], // 4.4: requested vs timed
    checkpointSyncSec: [2, 10],      // 4.4: sync phase seconds
    walBytesPerSec: [50 * 1024 ** 2, 200 * 1024 ** 2], // 4.4: WAL rate
    fpiShare: [0.3, 0.6],            // 4.4: full-page images per record
    tempBytesPerSec: [5 * 1024 ** 2, 50 * 1024 ** 2],   // 7 step 4: temp file rate
    dmlRowsPerSec: [5000, 50000],    // 4.2: rows changed per second
    hotSharePct: [50, 20],           // 4.2: HOT share on update-heavy tables (reversed)
    autovacuumIoShare: [0.3, 0.7],   // 4.1 item 6
    diskUsedPct: [80, 95],           // 4.3 space
    retainedWalBytes: [1 * 1024 ** 3, 10 * 1024 ** 3], // 4.5: slot retained WAL
    archiveLagSegments: [10, 100],   // 4.5: WAL waiting for archive
    logBytes: [10 * 1024 ** 3, 50 * 1024 ** 3],        // 10: log growth
    bloatPct: [20, 50],              // 9.3
    bloatMinWastedBytes: 256 * 1024 ** 2,
    deadTuplePct: [10, 30],          // 9.2
    deadTupleMinRows: 100000,
    vacuumOverdueFactor: [2, 10],    // 9.2: dead tuples over the threshold
    xidAgeShare: [0.4, 0.8],         // 9.4: age / 2^31
    sequencePct: [80, 95],           // 9.4: sequence exhaustion
    longTransactionSec: [600, 3600], // 5.6
    idleInTransactionSec: [60, 600], // 6
    preparedAgeSec: [600, 3600],     // 9.2
    slotXminAge: [1e6, 1e8],         // 9.2
    horizonAgeTx: [1e6, 1e8],        // 9.2
    lockWaitMs: [5000, 60000],       // 5.1
    blockedSessions: [3, 20],        // 5.1
    connectionsUsedPct: [80, 95],    // 6
    replayLagBytes: [64 * 1024 ** 2, 1024 ** 3], // 4.5
    replayLagSec: [10, 60],          // 4.5
    capacityPct: [80, 95],           // 4.5
    eolDays: [180, 0],               // 10: end of life (reversed)
    errorsPerMinute: [0.2, 2],       // health: ERROR rate in the log window
    fatalLogScore: 0.6,             // health: FATAL ends a session, PANIC/crash ends server operation
    terminationLogScore: 0.4,       // health: observed statement/lock timeouts or cancellations
    incidentLogScore: 1,            // 4.3 / health: explicit OOM, disk-full, crash or corruption evidence
    maintenanceAgeSec: [3600, 14400] // health: long maintenance
  };

  const SEVERITY_WEIGHT = {high: 1.0, critical: 1.0, medium: 0.6, moderate: 0.6, low: 0.3, info: 0.15, ok: 0, none: 0};
  const STATUS = {ok: "ok", warn: "warn", crit: "crit", noData: "no_data"};
  const XID_LIMIT = 2 ** 31;

  // ---------------------------------------------------------------- utilities

  function isFiniteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function toNumber(value) {
    if (isFiniteNumber(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    }
    if (typeof value === "boolean") {
      return value ? 1 : 0;
    }
    return null;
  }

  function clamp01(value) {
    return Math.max(0, Math.min(1, value));
  }

  // Linear 0..1 between warn and crit; reversed thresholds (warn > crit) mean "lower is worse".
  function scale(value, warn, crit) {
    if (!isFiniteNumber(value)) {
      return null;
    }
    if (warn === crit) {
      return value >= crit ? 1 : 0;
    }
    if (warn < crit) {
      return clamp01((value - warn) / (crit - warn));
    }
    return clamp01((warn - value) / (warn - crit));
  }

  function scalePair(value, pair) {
    return scale(value, pair[0], pair[1]);
  }

  function maxScore(...values) {
    let best = null;
    for (const value of values) {
      if (isFiniteNumber(value) && (best === null || value > best)) {
        best = value;
      }
    }
    return best;
  }

  function statusOf(score) {
    if (!isFiniteNumber(score)) {
      return STATUS.noData;
    }
    if (score < 0.34) {
      return STATUS.ok;
    }
    if (score < 0.67) {
      return STATUS.warn;
    }
    return STATUS.crit;
  }

  function fmtPct(value, digits) {
    return isFiniteNumber(value) ? value.toFixed(digits === undefined ? 1 : digits) + " %" : "n/a";
  }

  function fmtNum(value, digits) {
    if (!isFiniteNumber(value)) {
      return "n/a";
    }
    const abs = Math.abs(value);
    if (abs >= 1e9) return (value / 1e9).toFixed(2) + " G";
    if (abs >= 1e6) return (value / 1e6).toFixed(2) + " M";
    if (abs >= 1e4) return (value / 1e3).toFixed(1) + " k";
    return value.toFixed(digits === undefined ? (abs >= 100 ? 0 : 1) : digits);
  }

  function fmtBytes(value) {
    if (!isFiniteNumber(value)) {
      return "n/a";
    }
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let v = value;
    let i = 0;
    while (Math.abs(v) >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return v.toFixed(i === 0 ? 0 : 1) + " " + units[i];
  }

  function fmtSeconds(value) {
    if (!isFiniteNumber(value)) {
      return "n/a";
    }
    if (value >= 3600) return (value / 3600).toFixed(1) + " h";
    if (value >= 60) return (value / 60).toFixed(1) + " min";
    return value.toFixed(value >= 10 ? 0 : 1) + " s";
  }

  function truncate(text, length) {
    const value = String(text === null || text === undefined ? "" : text).replace(/\s+/g, " ").trim();
    return value.length > length ? value.slice(0, length - 1) + "…" : value;
  }

  function sumBy(rows, column) {
    let total = 0;
    let seen = false;
    for (const row of rows) {
      const value = toNumber(row[column]);
      if (value !== null) {
        total += value;
        seen = true;
      }
    }
    return seen ? total : null;
  }

  function maxBy(rows, column) {
    let best = null;
    let bestRow = null;
    for (const row of rows) {
      const value = toNumber(row[column]);
      if (value !== null && (best === null || value > best)) {
        best = value;
        bestRow = row;
      }
    }
    return {value: best, row: bestRow};
  }

  function topRows(rows, column, limit) {
    return rows
      .map((row) => ({row, value: toNumber(row[column])}))
      .filter((entry) => entry.value !== null)
      .sort((a, b) => b.value - a.value)
      .slice(0, limit === undefined ? 3 : limit);
  }

  function seriesStats(values) {
    const finite = values.filter(isFiniteNumber);
    if (finite.length === 0) {
      return null;
    }
    const sorted = finite.slice().sort((a, b) => a - b);
    const sum = finite.reduce((acc, value) => acc + value, 0);
    return {
      n: finite.length,
      sum,
      mean: sum / finite.length,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      p95: sorted[Math.min(sorted.length - 1, Math.floor(0.95 * (sorted.length - 1)))],
      last: finite[finite.length - 1]
    };
  }

  // Point-wise sum of several series (aligned by index; series may differ in length).
  function sumSeries(seriesList) {
    const length = Math.max(0, ...seriesList.map((series) => series.values.length));
    const out = [];
    for (let i = 0; i < length; i += 1) {
      let total = 0;
      let seen = false;
      for (const series of seriesList) {
        const value = series.values[i];
        if (isFiniteNumber(value)) {
          total += value;
          seen = true;
        }
      }
      out.push(seen ? total : NaN);
    }
    return out;
  }

  // ------------------------------------------------------ artifact accessors

  const rowCache = new WeakMap();
  const seriesCache = new WeakMap();

  function decodeCell(column, value) {
    if (value === null || value === undefined) {
      return null;
    }
    const encoding = column && column.encoding;
    if (encoding === "decimal_string") {
      return toNumber(value);
    }
    if (encoding === "json_number") {
      return isFiniteNumber(value) ? value : toNumber(value);
    }
    if (encoding === "json_boolean") {
      return typeof value === "boolean" ? value : value === "true" || value === "t";
    }
    return value;
  }

  function resultOf(item) {
    return item && typeof item === "object" && item.result && typeof item.result === "object" ? item.result : null;
  }

  function tableRows(item) {
    const result = resultOf(item);
    if (!result || result.kind !== "table" || !Array.isArray(result.rows) || !Array.isArray(result.columns)) {
      return [];
    }
    if (rowCache.has(result)) {
      return rowCache.get(result);
    }
    const columns = result.columns;
    const rows = result.rows.map((raw) => {
      const row = {};
      if (Array.isArray(raw)) {
        columns.forEach((column, index) => {
          row[column.name] = decodeCell(column, raw[index]);
        });
      } else if (raw && typeof raw === "object") {
        columns.forEach((column) => {
          row[column.name] = decodeCell(column, raw[column.name]);
        });
      }
      return row;
    });
    rowCache.set(result, rows);
    return rows;
  }

  function hasColumn(item, name) {
    const result = resultOf(item);
    return Boolean(result && Array.isArray(result.columns) && result.columns.some((column) => column.name === name));
  }

  function chartSeries(item) {
    const result = resultOf(item);
    if (!result || result.kind !== "chart" || !Array.isArray(result.series)) {
      return [];
    }
    if (seriesCache.has(result)) {
      return seriesCache.get(result);
    }
    const list = result.series.map((series) => {
      const points = Array.isArray(series.points) ? series.points : [];
      const values = points.map((point) => toNumber(point && point.value));
      return {
        name: String(series.name === undefined ? series.label || "" : series.name),
        label: String(series.label === undefined ? series.name || "" : series.label),
        unit: series.unit || (result.chart && result.chart.unit) || null,
        values: values.map((value) => (value === null ? NaN : value)),
        finite: values.filter(isFiniteNumber).length,
        times: points.map((point) => (point ? point.t : null))
      };
    });
    seriesCache.set(result, list);
    return list;
  }

  function textOf(item) {
    const result = resultOf(item);
    if (!result) {
      return "";
    }
    if (typeof result.data === "string") {
      return result.data;
    }
    if (typeof result.text === "string") {
      return result.text;
    }
    if (Array.isArray(result.lines)) {
      return result.lines.join("\n");
    }
    return "";
  }

  function itemPresence(item) {
    if (!item) {
      return "absent";
    }
    const status = item.collection_status || "unknown";
    if (status === "skipped" || status === "unsupported" || status === "error") {
      return status;
    }
    const result = resultOf(item);
    if (!result) {
      return "empty";
    }
    if (result.kind === "table") {
      return Array.isArray(result.rows) && result.rows.length > 0 ? "present" : "empty";
    }
    if (result.kind === "chart") {
      const eventChart = ["log_event", "query_event"].includes((result.chart || {}).tooltip_kind);
      return chartSeries(item).some((series) => series.finite >= (eventChart ? 1 : 2)) ? "present" : "empty";
    }
    return textOf(item).trim() !== "" ? "present" : "empty";
  }

  // ------------------------------------------------------------- facts

  const PROCESS_PATTERNS = [
    [/checkpointer/i, "checkpointer"],
    [/background writer/i, "bgwriter"],
    [/walwriter/i, "walwriter"],
    [/autovacuum launcher/i, "autovacuum_launcher"],
    [/autovacuum worker/i, "autovacuum"],
    [/walsender/i, "walsender"],
    [/walreceiver/i, "walreceiver"],
    [/logger/i, "logger"],
    [/io worker/i, "io_worker"],
    [/stats collector/i, "stats_collector"],
    [/archiver/i, "archiver"],
    [/parallel worker/i, "parallel_worker"],
    [/logical replication/i, "logical_replication"],
    [/startup/i, "startup"],
    [/slotsync/i, "slotsync"],
    [/summarizer/i, "wal_summarizer"],
    [/pg_wait_sampling/i, "wait_sampling"]
  ];

  function classifyProcess(command) {
    const text = String(command || "");
    if (!text.startsWith("postgres:")) {
      return /^postgres(\s|$)|postmaster/.test(text) ? "postmaster" : "other";
    }
    for (const [pattern, kind] of PROCESS_PATTERNS) {
      if (pattern.test(text)) {
        return kind;
      }
    }
    return "client";
  }

  function settingValue(rows, name) {
    const row = rows.find((candidate) => candidate.setting_name === name || candidate.name === name);
    if (!row) {
      return null;
    }
    const normalized = toNumber(row.setting_normalized);
    return {
      name,
      raw: row.setting_value === undefined ? row.setting : row.setting_value,
      value: normalized,
      unit: row.unit_normalized || null,
      bool: /^(on|true|yes|1)$/i.test(String(row.setting_value === undefined ? row.setting : row.setting_value))
    };
  }

  function makeFacts(ctx) {
    const cache = {};
    function memo(name, compute) {
      if (!(name in cache)) {
        cache[name] = compute();
      }
      return cache[name];
    }
    return {
      cpuCores() {
        return memo("cpuCores", () => {
          const text = ctx.text("os.cpu_info");
          const match = /^CPU\(s\):\s+(\d+)/m.exec(text);
          if (match) {
            return Number(match[1]);
          }
          const rows = ctx.rows("os.lshw_processor");
          for (const row of rows) {
            const cores = /cores=(\d+)/.exec(String(row.configuration || ""));
            const threads = /threads=(\d+)/.exec(String(row.configuration || ""));
            if (threads) return Number(threads[1]);
            if (cores) return Number(cores[1]);
          }
          return null;
        });
      },
      cpuModel() {
        return memo("cpuModel", () => {
          const match = /^Model name:\s+(.+)$/m.exec(ctx.text("os.cpu_info"));
          if (match) return match[1].trim();
          const rows = ctx.rows("os.lshw_processor");
          return rows.length ? String(rows[0].product || "") : null;
        });
      },
      memory() {
        return memo("memory", () => {
          const rows = ctx.rows("os.memory_info");
          const get = (metric) => {
            const row = rows.find((candidate) => candidate.metric === metric);
            return row ? toNumber(row.value_normalized) : null;
          };
          let total = get("MemTotal");
          if (total === null) {
            const ram = ctx.rows("os.total_ram");
            total = ram.length ? toNumber(ram[0].total_ram_bytes) : null;
          }
          return {
            total,
            available: get("MemAvailable"),
            free: get("MemFree"),
            swapTotal: get("SwapTotal"),
            swapFree: get("SwapFree"),
            cached: get("Cached"),
            anonHugePages: get("AnonHugePages"),
            pageTables: get("PageTables")
          };
        });
      },
      diskMedia() {
        return memo("diskMedia", () => {
          const media = {};
          for (const row of ctx.rows("os.lshw_disk")) {
            const name = String(row.logicalname || row.id || "");
            const description = String(row.description || "") + " " + String(row.product || "");
            let kind = "unknown";
            if (/nvme/i.test(description) || /nvme/i.test(name)) kind = "nvme";
            else if (/ssd|solid/i.test(description)) kind = "ssd";
            else if (/rotational=1|hdd|scsi disk|ata disk/i.test(description + " " + String(row.configuration || ""))) kind = "hdd";
            if (name) {
              media[name.replace(/^\/dev\//, "")] = kind;
            }
          }
          return media;
        });
      },
      mediaFor(device) {
        const media = this.diskMedia();
        const name = String(device || "").replace(/^\/dev\//, "");
        if (media[name]) return media[name];
        for (const key of Object.keys(media)) {
          if (name.startsWith(key) || key.startsWith(name)) return media[key];
        }
        if (/^nvme/i.test(name)) return "nvme";
        return "unknown";
      },
      pgConfig() {
        return memo("pgConfig", () => {
          const rows = ctx.rows("overview.pg_config");
          const map = {};
          for (const row of rows) {
            map[String(row.parameter || "").toUpperCase()] = String(row.value === null || row.value === undefined ? "" : row.value);
          }
          const configure = map.CONFIGURE || "";
          const cflags = map.CFLAGS || "";
          return {
            configure,
            cflags,
            version: map.VERSION || null,
            cassert: /--enable-cassert/.test(configure),
            debug: /--enable-debug/.test(configure),
            noOptimization: /(^|\s)-O0(\s|$)/.test(cflags)
          };
        });
      },
      processTree() {
        return memo("processTree", () => {
          const text = ctx.text("backend_os.postgres_process_tree");
          const counts = {};
          const lines = [];
          for (const line of text.split("\n")) {
            const match = /^\s*(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+(\S+)\s+(.*)$/.exec(line);
            if (!match) continue;
            const command = match[9].trim();
            const kind = classifyProcess(command);
            counts[kind] = (counts[kind] || 0) + 1;
            lines.push({pid: Number(match[1]), user: match[3], cpu: Number(match[6]), mem: Number(match[7]), command, kind});
          }
          return {counts, lines};
        });
      },
      setting(name) {
        return settingValue(ctx.rows("overview.pg_settings"), name);
      },
      hugePages() {
        return memo("hugePages", () => {
          const rows = ctx.rows("os.postgresql_huge_pages");
          return rows.length ? rows[0] : null;
        });
      },
      windowSeconds() {
        return memo("windowSeconds", () => {
          const runtime = ctx.runtime;
          const duration = toNumber(runtime.duration_seconds);
          if (duration !== null && duration > 0) return duration;
          const start = Date.parse(runtime.snapshot_window_started_at || runtime.started_at || "");
          const finish = Date.parse(runtime.snapshot_window_finished_at || runtime.finished_at || "");
          if (Number.isFinite(start) && Number.isFinite(finish) && finish > start) {
            return (finish - start) / 1000;
          }
          return null;
        });
      }
    };
  }

  // ------------------------------------------------------------ evaluators

  // Every evaluator receives a context with helpers and returns a score in [0, 1]
  // or null (no evidence). Reasons, facts and evidence are pushed into the context.

  function seriesByPrefix(ctx, itemId, prefix) {
    return ctx.series(itemId).filter((series) => series.name.toLowerCase().startsWith(prefix.toLowerCase()));
  }

  function seriesNamed(ctx, itemId, name) {
    const lower = name.toLowerCase();
    return ctx.series(itemId).find((series) => series.name.toLowerCase() === lower) || null;
  }

  function seriesTotalStats(ctx, itemId, prefix) {
    const list = prefix === undefined ? ctx.series(itemId) : seriesByPrefix(ctx, itemId, prefix);
    if (!list.length) return null;
    return seriesStats(sumSeries(list));
  }

  function cpuBusyStats(ctx) {
    const idle = seriesNamed(ctx, "snapshot_charts_os.os_cpu_utilization", "idle");
    const iowait = seriesNamed(ctx, "snapshot_charts_os.os_cpu_utilization", "iowait");
    const steal = seriesNamed(ctx, "snapshot_charts_os.os_cpu_utilization", "steal");
    if (idle) {
      return seriesStats(idle.values.map((value, index) => {
        const waitValue = iowait ? iowait.values[index] : 0;
        const stealValue = steal ? steal.values[index] : 0;
        return [value, waitValue, stealValue].every(isFiniteNumber)
          ? Math.max(0, 100 - value - waitValue - stealValue) : NaN;
      }));
    }
    const parts = ctx.series("snapshot_charts_os.os_cpu_utilization").filter((series) => !/^(idle|iowait|steal)$/i.test(series.name));
    return parts.length ? seriesStats(sumSeries(parts)) : null;
  }

  function backendCpuRows(ctx) {
    return ctx.rows("backend_os.backend_proc_cpu").map((row) => ({
      row,
      kind: classifyProcess(row.command || row.process),
      cpu: toNumber(row.avg_cpu_pct) || 0
    }));
  }

  function cpuShareScore(ctx, kinds, thresholds, label) {
    const rows = backendCpuRows(ctx).filter((entry) => kinds.includes(entry.kind));
    if (!rows.length) {
      if (ctx.presence("backend_os.backend_proc_cpu") === "present") {
        ctx.reason(label + ": none among the sampled processes", "backend_os.backend_proc_cpu");
        return 0;
      }
      return null;
    }
    const cores = ctx.facts.cpuCores();
    const total = rows.reduce((acc, entry) => acc + entry.cpu, 0);
    const share = cores ? total / (cores * 100) : null;
    ctx.fact(label + " CPU", fmtPct(total, 0) + (cores ? " of " + cores * 100 + " %" : ""));
    const top = rows.sort((a, b) => b.cpu - a.cpu).slice(0, 3)
      .map((entry) => truncate(entry.row.command || entry.row.process, 60) + " (" + fmtPct(entry.cpu, 0) + ")");
    ctx.reason(label + ": " + rows.length + " process(es) at " + fmtPct(total, 0) + " CPU" + (share !== null ? " (" + fmtPct(share * 100, 0) + " of all cores)" : "") + "; top: " + top.join(", "), "backend_os.backend_proc_cpu");
    if (share === null) {
      return scalePair(total, [thresholds[0] * 400, thresholds[1] * 400]);
    }
    return scalePair(share, thresholds);
  }

  function findingsScore(ctx, options) {
    const roles = (options && options.roles) || ["primary", "support"];
    let best = null;
    for (const binding of ctx.node.bindings) {
      if (!roles.includes(binding.role) || binding.role === "fact") continue;
      if (options && options.excludeItems && options.excludeItems.includes(binding.id)) continue;
      if (options && options.weightedOnly && typeof binding.weight !== "number") continue;
      const item = ctx.item(binding.id);
      if (ctx.presence(binding.id) !== "present") continue;
      const rows = ctx.rows(binding.id);
      if (!rows.length) continue;
      let severity = null;
      if (hasColumn(item, "risk_level")) {
        for (const row of rows) {
          const level = String(row.risk_level || "").toLowerCase();
          const weight = SEVERITY_WEIGHT[level];
          if (weight !== undefined && (severity === null || weight > severity)) severity = weight;
        }
        if (severity === null) severity = 0;
      } else if (typeof binding.weight === "number") {
        // A weight of 1 marks findings that are critical on their own (one leaked secret
        // is enough); lighter weights grow with the number of rows.
        severity = binding.weight >= 1 ? 1 : binding.weight * (0.6 + 0.4 * Math.min(1, rows.length / 10));
      } else if (options && options.rowsAreFindings) {
        severity = 0.6 * (0.6 + 0.4 * Math.min(1, rows.length / 10));
      } else {
        continue;
      }
      if (severity > 0) {
        const worst = hasColumn(item, "risk_level")
          ? "worst risk " + (severity >= 1 ? "high" : severity >= 0.6 ? "medium" : "low")
          : "weight " + severity.toFixed(2);
        ctx.reason(ctx.title(binding.id) + ": " + rows.length + " finding row(s), " + worst, binding.id);
      }
      best = maxScore(best, severity);
    }
    return best;
  }

  // These tables contain mixed observations, not homogeneous finding rows.
  // Keep their bindings as context, but score only evidence for this branch.
  const MIXED_LOG_ITEMS = ["server_log.system_incidents", "server_log.server_lifecycle", "server_log.crash_recovery_events"];
  const CORRUPTION_TYPES = ["data_corruption", "index_corruption", "checksum_failure", "wal_corruption"];
  const CRASH_TYPES = ["unclean_shutdown", "crash_recovery", "backend_crash", "backend_crash_cleanup", "startup_failure", "configuration_error"];

  function logSignalMatches(row, category) {
    const type = String(row.incident_type || "");
    const event = String(row.event_type || "");
    const message = String(row.message || "");
    if (category === "memory") {
      return type ? type === "out_of_memory" : /out of memory|cannot allocate memory|oom[- ]kill/i.test(message);
    }
    if (category === "space") {
      return type ? type === "disk_full" : /no space left on device|disk quota exceeded/i.test(message);
    }
    if (String(row.severity).toUpperCase() === "PANIC") return true;
    if (type) return CORRUPTION_TYPES.includes(type);
    if (event) return CRASH_TYPES.includes(event);
    // Compatibility crash_recovery_events has no event_type. A redo start alone
    // is normal on a standby; a SIGKILL proves a crash, but does not prove OOM.
    return /terminated by signal|was not properly shut down|automatic recovery in progress|terminating any other active server processes|invalid page|checksum failure|incorrect checksum/i.test(message);
  }

  function logSignalScore(ctx, category) {
    let score = null;
    const label = {memory: "Out-of-memory", space: "Disk-full", crash: "Crash or corruption"}[category];
    for (const binding of ctx.node.bindings) {
      if (binding.role === "fact" || !MIXED_LOG_ITEMS.includes(binding.id) || ctx.presence(binding.id) !== "present") continue;
      const rows = ctx.rows(binding.id).filter((row) => logSignalMatches(row, category));
      if (!rows.length) continue;
      score = THRESHOLDS.incidentLogScore;
      const count = rows.reduce((total, row) => total + (toNumber(row.occurrences ?? row.repeat_count) || 1), 0);
      ctx.reason(label + ": " + count + " event(s) in " + ctx.title(binding.id), binding.id);
    }
    return score;
  }

  // Shared calculations must replay their explanations into every consuming
  // node. Caching only the score makes later branches red without evidence.
  function cachedEvaluation(ctx, key, compute) {
    if (ctx.shared[key] === undefined) {
      const reasons = [];
      const facts = [];
      const recording = Object.assign({}, ctx, {
        reason: (text, itemId) => reasons.push([text, itemId]),
        fact: (name, value) => facts.push([name, value])
      });
      ctx.shared[key] = {value: compute(recording), reasons, facts};
    }
    const cached = ctx.shared[key];
    for (const [text, itemId] of cached.reasons) ctx.reason(text, itemId);
    for (const [name, value] of cached.facts) ctx.fact(name, value);
    return cached.value;
  }

  const evaluators = {
    aggregate() {
      return null;
    },

    generic(ctx) {
      const score = findingsScore(ctx);
      if (score === null) {
        const collected = ctx.node.bindings.filter((b) => b.role !== "fact" && ["present", "empty"].includes(ctx.presence(b.id)));
        if (collected.length) {
          ctx.reason("No findings in " + collected.length + " collected item(s)");
          return 0;
        }
      }
      return score;
    },

    platform_facts(ctx) {
      const tree = ctx.facts.processTree();
      const kernel = truncate(ctx.text("os.kernel_version"), 80);
      const release = /PRETTY_NAME="?([^"\n]+)"?/.exec(ctx.text("os.os_release"));
      if (kernel) ctx.fact("Kernel", kernel);
      if (release) ctx.fact("OS", release[1]);
      const version = ctx.rows("overview.server_version");
      if (version.length) ctx.fact("PostgreSQL", truncate(version[0].version, 80));
      if (tree.lines.length) {
        ctx.fact("PostgreSQL processes", Object.entries(tree.counts).map(([kind, count]) => kind + " " + count).join(", "));
        ctx.reason(tree.lines.length + " PostgreSQL processes: " + (tree.counts.client || 0) + " client backends, " + (tree.counts.autovacuum || 0) + " autovacuum workers, " + (tree.counts.walsender || 0) + " WAL senders", "backend_os.postgres_process_tree");
      }
      const volume = ctx.rows("overview.database_volume");
      if (volume.length) {
        const total = sumBy(volume, "database_size_bytes");
        ctx.fact("Databases", volume.length + ", " + fmtBytes(total));
      }
      return ctx.anyCollected() ? 0 : null;
    },

    build_facts(ctx) {
      const config = ctx.facts.pgConfig();
      const cores = ctx.facts.cpuCores();
      const model = ctx.facts.cpuModel();
      if (cores) ctx.fact("CPU cores", String(cores));
      if (model) ctx.fact("CPU model", model);
      if (!config.configure && !ctx.rows("overview.pg_config").length) {
        return cores || model ? 0 : null;
      }
      let score = 0;
      if (config.cassert) {
        ctx.reason("Build has --enable-cassert: assertion checks cost 30-50 % of CPU; use a production build", "overview.pg_config");
        score = 1;
      }
      if (config.noOptimization) {
        ctx.reason("CFLAGS contain -O0: unoptimized build", "overview.pg_config");
        score = Math.max(score, 0.6);
      }
      if (config.debug) {
        ctx.reason("Build has --enable-debug (symbols only, harmless without cassert)", "overview.pg_config");
        score = Math.max(score, 0.15);
      }
      if (config.version) ctx.fact("pg_config version", config.version);
      if (score === 0) ctx.reason("Build flags look like a production build");
      return score;
    },

    cpu_utilization(ctx) {
      const busy = cpuBusyStats(ctx);
      const cores = ctx.facts.cpuCores();
      let score = null;
      if (busy) {
        score = maxScore(score, scalePair(busy.p95, THRESHOLDS.cpuBusyPct));
        ctx.reason("CPU busy p95 " + fmtPct(busy.p95, 0) + ", mean " + fmtPct(busy.mean, 0) + " over " + busy.n + " samples", "snapshot_charts_os.os_cpu_utilization");
        ctx.fact("CPU busy p95", fmtPct(busy.p95, 0));
      }
      const steal = seriesNamed(ctx, "snapshot_charts_os.os_cpu_utilization", "steal");
      if (steal) {
        const stats = seriesStats(steal.values);
        if (stats && stats.p95 > 1) {
          score = maxScore(score, scalePair(stats.p95, THRESHOLDS.cpuStealPct));
          ctx.reason("Hypervisor steal p95 " + fmtPct(stats.p95, 0) + ": the host takes CPU away", "snapshot_charts_os.os_cpu_utilization");
        }
      }
      const load1 = seriesNamed(ctx, "snapshot_charts_os.os_cpu_load", "load1");
      if (load1) {
        const stats = seriesStats(load1.values);
        if (stats) {
          const perCore = cores ? stats.mean / cores : null;
          if (perCore !== null) {
            score = maxScore(score, scalePair(perCore, THRESHOLDS.cpuLoadPerCore));
            ctx.reason("load1 mean " + stats.mean.toFixed(2) + " on " + cores + " cores (" + perCore.toFixed(2) + " per core)", "snapshot_charts_os.os_cpu_load");
          } else {
            ctx.reason("load1 mean " + stats.mean.toFixed(2) + " (core count unknown: os.cpu_info missing)", "snapshot_charts_os.os_cpu_load");
          }
          ctx.fact("load1 mean", stats.mean.toFixed(2));
        }
      }
      if (cores) ctx.fact("CPU cores", String(cores));
      return score;
    },

    cpu_user(ctx) {
      const score = cpuComponent(ctx, ["user", "nice"], THRESHOLDS.cpuBusyPct, "User CPU");
      const load = seriesNamed(ctx, "snapshot_charts_os.os_cpu_load", "load1");
      const stats = load && seriesStats(load.values);
      const cores = ctx.facts.cpuCores();
      if (cores) ctx.fact("CPU cores", String(cores));
      if (stats) {
        ctx.fact("load1 mean", stats.mean.toFixed(2));
        ctx.reason("Load average includes I/O waits as well as runnable tasks; it does not establish user CPU saturation", "snapshot_charts_os.os_cpu_load");
      }
      return score;
    },

    cpu_system(ctx) {
      const score = cpuComponent(ctx, ["system", "irq", "softirq"], THRESHOLDS.cpuSystemPct, "System CPU");
      const kernel = seriesTotalStats(ctx, "snapshot_charts_db.database_kernel_cpu_rate", "system");
      if (kernel) ctx.fact("PostgreSQL kernel CPU", fmtNum(kernel.mean, 2) + " CPU s/s");
      return score;
    },

    cpu_iowait(ctx) {
      const score = cpuComponent(ctx, ["iowait"], THRESHOLDS.cpuIowaitPct, "I/O wait");
      if (score !== null) ctx.reason("I/O wait is idle CPU time with outstanding I/O, not CPU work. The children are possible contributors; confirm them with I/O and memory evidence.");
      return score;
    },

    cpu_steal(ctx) {
      return cpuComponent(ctx, ["steal"], THRESHOLDS.cpuStealPct, "Hypervisor steal");
    },

    memory_available(ctx) {
      return maxScore(memoryAvailable(ctx), logSignalScore(ctx, "memory"));
    },

    swap_usage(ctx) {
      return swapUsage(ctx);
    },

    cpu_backends(ctx) {
      return cpuShareScore(ctx, ["client", "parallel_worker"], THRESHOLDS.backendCpuShare, "Client backends");
    },

    cpu_autovacuum(ctx) {
      const score = cpuShareScore(ctx, ["autovacuum"], THRESHOLDS.autovacuumCpuShare, "Autovacuum workers");
      const progress = ctx.rows("maintenance_progress.vacuum_progress");
      if (progress.length) {
        const wrap = progress.filter((row) => row.anti_wraparound === true).length;
        ctx.reason(progress.length + " vacuum operation(s) in progress" + (wrap ? ", " + wrap + " anti-wraparound" : ""), "maintenance_progress.vacuum_progress");
      }
      const runs = ctx.rows("server_log.autovacuum_runs");
      if (runs.length) ctx.fact("Autovacuum runs in log window", String(runs.length));
      return score;
    },

    cpu_walsender(ctx) {
      let score = cpuShareScore(ctx, ["walsender"], THRESHOLDS.walsenderCpuShare, "WAL senders");
      const spills = ctx.rows("snapshot_delta_workload.logical_decoding_slot_delta");
      const spillRate = sumBy(spills, "spill_bytes_per_sec");
      if (spillRate !== null && spillRate > 0) {
        score = maxScore(score, 0.3);
        ctx.reason("Logical decoding spills " + fmtBytes(spillRate) + "/s to disk: raise logical_decoding_work_mem", "snapshot_delta_workload.logical_decoding_slot_delta");
      }
      return score;
    },

    other_processes(ctx) {
      const busy = cpuBusyStats(ctx);
      const rows = backendCpuRows(ctx);
      const cores = ctx.facts.cpuCores();
      if (!busy || !rows.length || !cores) {
        return null;
      }
      const pgPct = rows.reduce((acc, entry) => acc + entry.cpu, 0) / cores;
      const otherPct = Math.max(0, busy.mean - pgPct);
      ctx.fact("PostgreSQL CPU", fmtPct(pgPct, 0) + " of host");
      ctx.fact("Other CPU", fmtPct(otherPct, 0) + " of host");
      if (busy.mean < 30) {
        ctx.reason("Host CPU mean " + fmtPct(busy.mean, 0) + ": no competing load to speak of");
        return 0;
      }
      ctx.reason("Host busy " + fmtPct(busy.mean, 0) + ", PostgreSQL processes " + fmtPct(pgPct, 0) + ": " + fmtPct(otherPct, 0) + " belongs to other processes", "backend_os.backend_proc_cpu");
      return scalePair(otherPct, THRESHOLDS.otherCpuPct);
    },

    heavy_queries(ctx) {
      return damp(ctx, heavyQueries(ctx), "cpu");
    },

    seq_scans(ctx) {
      return damp(ctx, seqScans(ctx), "cpu");
    },

    index_efficiency(ctx) {
      return damp(ctx, indexEfficiency(ctx), "cpu");
    },

    light_queries(ctx) {
      return damp(ctx, lightQueries(ctx), "cpu");
    },

    jit_parallel(ctx) {
      return damp(ctx, jitParallel(ctx), "cpu");
    },

    contention(ctx) {
      return damp(ctx, contention(ctx), "cpu");
    },

    session_churn(ctx) {
      return damp(ctx, sessionChurn(ctx), "cpu");
    },

    network_traffic(ctx) {
      return damp(ctx, networkTraffic(ctx), "cpu");
    },

    work_mem_budget(ctx) {
      return damp(ctx, workMemBudget(ctx), "ram");
    }
  };

  // Cause evaluators: raw signal without resource pressure applied.
  const causes = {
    heavy_queries(ctx) {
      let score = null;
      const total = ctx.rows("sql_workload.top_sql_by_total_time");
      if (total.length) {
        const sum = sumBy(total, "total_exec_time_ms");
        const top = topRows(total, "total_exec_time_ms", 3);
        if (sum && top.length) {
          const share = top[0].value / sum;
          score = maxScore(score, scalePair(share, THRESHOLDS.topStatementShare) * 0.6);
          ctx.reason("Top statement holds " + fmtPct(share * 100, 0) + " of the listed execution time (query_id " + top[0].row.query_id + ", " + fmtNum(top[0].row.calls) + " calls)", "sql_workload.top_sql_by_total_time");
        }
      }
      const mean = ctx.rows("sql_workload.top_sql_by_mean_time");
      if (mean.length) {
        const slowest = maxBy(mean, "mean_exec_time_ms");
        if (slowest.value !== null) {
          score = maxScore(score, scalePair(slowest.value, THRESHOLDS.meanExecMs));
          ctx.reason("Slowest statement mean " + fmtNum(slowest.value, 0) + " ms (query_id " + slowest.row.query_id + ")", "sql_workload.top_sql_by_mean_time");
          ctx.fact("Slowest mean", fmtNum(slowest.value, 0) + " ms");
        }
      }
      const delta = ctx.rows("snapshot_delta_workload.sql_time_delta");
      if (delta.length) {
        const top = topRows(delta, "exec_time_ms_per_sec", 1);
        if (top.length) {
          ctx.reason("Busiest statement in the window: " + fmtNum(top[0].value, 0) + " ms of execution per second (query_id " + top[0].row.query_id + ")", "snapshot_delta_workload.sql_time_delta");
          score = maxScore(score, scale(top[0].value, 1000, 4000) * 0.6);
        }
      }
      const events = ctx.rows("server_log.query_resource_events");
      if (events.length) ctx.fact("Slow statements in log", String(events.length));
      return score;
    },

    seq_scans_raw(ctx) {
      const rows = ctx.rows("object_workload.table_workload").filter((row) => (toNumber(row.n_live_tup) || 0) > 10000);
      const deltas = ctx.rows("snapshot_delta_workload.table_scan_delta");
      let score = null;
      if (rows.length) {
        let seq = 0;
        let idx = 0;
        const offenders = [];
        for (const row of rows) {
          const seqTup = toNumber(row.seq_tup_read) || 0;
          const idxTup = toNumber(row.idx_tup_fetch) || 0;
          seq += seqTup;
          idx += idxTup;
          if (seqTup > idxTup && seqTup > 1e6) offenders.push({name: row.schemaname + "." + row.relname, seqTup});
        }
        const share = seq + idx > 0 ? seq / (seq + idx) : 0;
        offenders.sort((a, b) => b.seqTup - a.seqTup);
        score = maxScore(score, scalePair(share, THRESHOLDS.seqShare), scalePair(offenders.length, THRESHOLDS.seqTables));
        ctx.fact("Seq share (tables > 10k rows)", fmtPct(share * 100, 0));
        ctx.reason(offenders.length + " table(s) above 10k rows read more tuples sequentially than by index" + (offenders.length ? ": " + offenders.slice(0, 3).map((o) => o.name).join(", ") : "") + "; sequential share " + fmtPct(share * 100, 0), "object_workload.table_workload");
      }
      if (deltas.length) {
        const top = topRows(deltas, "seq_tup_read_per_sec", 3).filter((entry) => entry.value > 0);
        if (top.length) {
          ctx.reason("Sequential reads in the window: " + top.map((entry) => entry.row.schemaname + "." + entry.row.relname + " " + fmtNum(entry.value, 0) + " rows/s").join(", "), "snapshot_delta_workload.table_scan_delta");
          score = maxScore(score, scale(top[0].value, 100000, 1000000) * 0.6);
        }
      }
      return score;
    },

    index_efficiency_raw(ctx) {
      let score = null;
      const rows = ctx.rows("object_workload.index_workload");
      if (rows.length) {
        const bad = [];
        for (const row of rows) {
          const read = toNumber(row.idx_tup_read) || 0;
          const fetch = toNumber(row.idx_tup_fetch) || 0;
          if (fetch > 0 && read > 100000 && read / fetch > THRESHOLDS.idxScale) {
            bad.push({name: row.schemaname + "." + row.indexrelname, ratio: read / fetch});
          }
        }
        bad.sort((a, b) => b.ratio - a.ratio);
        score = maxScore(score, scalePair(bad.length, THRESHOLDS.idxScaleCount) * 0.6);
        ctx.reason(bad.length + " index(es) read over " + THRESHOLDS.idxScale + " entries per fetched row" + (bad.length ? ": " + bad.slice(0, 3).map((b) => b.name + " (" + fmtNum(b.ratio, 0) + ")").join(", ") : ""), "object_workload.index_workload");
        ctx.fact("Indexes with idx_scale > 100", String(bad.length));
      }
      score = maxScore(score, findingsScore(ctx, {roles: ["support"], weightedOnly: true}));
      return score;
    },

    light_queries_raw(ctx) {
      let score = null;
      const tps = seriesTotalStats(ctx, "snapshot_charts_db.database_transaction_rate");
      if (tps) {
        score = maxScore(score, scalePair(tps.p95, THRESHOLDS.tpsHigh));
        ctx.reason("Transactions p95 " + fmtNum(tps.p95, 0) + "/s, mean " + fmtNum(tps.mean, 0) + "/s", "snapshot_charts_db.database_transaction_rate");
        ctx.fact("TPS p95", fmtNum(tps.p95, 0));
      }
      const calls = ctx.rows("sql_workload.top_sql_by_calls");
      if (calls.length) {
        const top = topRows(calls, "calls", 1)[0];
        if (top) {
          const mean = toNumber(top.row.mean_exec_time_ms);
          ctx.reason("Most frequent statement: " + fmtNum(top.value, 0) + " calls, mean " + (mean === null ? "n/a" : mean.toFixed(3) + " ms") + " (query_id " + top.row.query_id + ")", "sql_workload.top_sql_by_calls");
        }
      }
      const switches = ctx.rows("snapshot_delta_workload.sql_context_switches_delta");
      if (switches.length) {
        const rate = sumBy(switches, "voluntary_switches_per_sec");
        if (rate !== null) {
          ctx.fact("Voluntary context switches", fmtNum(rate, 0) + "/s");
          score = maxScore(score, scale(rate, 20000, 100000) * 0.6);
        }
      }
      return score;
    },

    jit_parallel_raw(ctx) {
      const jit = ctx.facts.setting("jit");
      const gather = ctx.facts.setting("max_parallel_workers_per_gather");
      if (!jit && !gather) return null;
      let score = 0;
      if (jit) ctx.fact("jit", String(jit.raw));
      if (gather) ctx.fact("max_parallel_workers_per_gather", String(gather.raw));
      const rows = ctx.rows("sql_workload.top_sql_by_total_time");
      const shortParallel = rows.filter((row) => (toNumber(row.parallel_workers_launched) || 0) > 0 && (toNumber(row.mean_exec_time_ms) || 0) < 100);
      if (shortParallel.length) {
        score = Math.max(score, 0.4);
        ctx.reason(shortParallel.length + " statement(s) under 100 ms launch parallel workers", "sql_workload.top_sql_by_total_time");
      }
      if (jit && jit.bool) {
        ctx.reason("jit = on: check EXPLAIN (ANALYZE) of short statements for JIT time; jit = off is the safe OLTP default", "overview.pg_settings");
        score = Math.max(score, 0.15);
      } else {
        ctx.reason("jit is off");
      }
      return score;
    },

    system_time(ctx) {
      let score = null;
      const system = seriesNamed(ctx, "snapshot_charts_os.os_cpu_utilization", "system");
      if (system) {
        const stats = seriesStats(system.values);
        if (stats) {
          score = maxScore(score, scalePair(stats.p95, THRESHOLDS.cpuSystemPct));
          ctx.reason("System CPU p95 " + fmtPct(stats.p95, 0) + ", mean " + fmtPct(stats.mean, 0), "snapshot_charts_os.os_cpu_utilization");
          ctx.fact("System CPU p95", fmtPct(stats.p95, 0));
        }
      }
      const user = seriesTotalStats(ctx, "snapshot_charts_db.database_kernel_cpu_rate", "user");
      const kernel = seriesTotalStats(ctx, "snapshot_charts_db.database_kernel_cpu_rate", "system");
      if (user && kernel && user.mean + kernel.mean > 0) {
        const share = kernel.mean / (user.mean + kernel.mean);
        score = maxScore(score, scalePair(share, THRESHOLDS.kernelShare));
        ctx.reason("Kernel share of PostgreSQL CPU " + fmtPct(share * 100, 0) + " (pg_stat_kcache)", "snapshot_charts_db.database_kernel_cpu_rate");
      }
      const faults = seriesTotalStats(ctx, "snapshot_charts_db.database_page_fault_rate");
      if (faults) ctx.fact("Page faults", fmtNum(faults.mean, 0) + "/s");
      return score;
    },

    network_traffic_raw(ctx) {
      const packets = seriesTotalStats(ctx, "snapshot_charts_os.os_network_packets");
      if (!packets) return null;
      const rx = seriesTotalStats(ctx, "snapshot_charts_os.os_network_receive");
      const tx = seriesTotalStats(ctx, "snapshot_charts_os.os_network_transmit");
      ctx.reason("Packets p95 " + fmtNum(packets.p95, 0) + "/s" + (rx ? ", rx " + fmtBytes(rx.mean) + "/s" : "") + (tx ? ", tx " + fmtBytes(tx.mean) + "/s" : ""), "snapshot_charts_os.os_network_packets");
      ctx.fact("Packets p95", fmtNum(packets.p95, 0) + "/s");
      return scalePair(packets.p95, THRESHOLDS.packetsPerSec);
    },

    contention_raw(ctx) {
      let score = null;
      const rows = ctx.rows("activity_locks.wait_events");
      const lwlockTypes = ["LWLock", "BufferPin", "Buffer", "IPC"];
      if (rows.length) {
        const waiting = rows.filter((row) => lwlockTypes.includes(String(row.wait_event_type)));
        const sessions = sumBy(waiting, "sessions") || 0;
        score = maxScore(score, scalePair(sessions, THRESHOLDS.lwlockSessions));
        const top = topRows(waiting, "sessions", 3).map((entry) => entry.row.wait_event_type + ":" + entry.row.wait_event + " x" + entry.value);
        ctx.reason(sessions + " session(s) in LWLock/Buffer/IPC waits" + (top.length ? ": " + top.join(", ") : ""), "activity_locks.wait_events");
      }
      const profile = ctx.series("activity_locks.wait_event_sample_profile");
      if (profile.length) {
        const lw = profile.filter((series) => lwlockTypes.some((type) => series.name.startsWith(type)));
        const all = seriesStats(sumSeries(profile));
        const lwStats = lw.length ? seriesStats(sumSeries(lw)) : null;
        if (all && lwStats && all.mean > 0) {
          const share = lwStats.mean / all.mean;
          score = maxScore(score, scalePair(share * 100, THRESHOLDS.lwlockSharePct), scalePair(lwStats.p95, THRESHOLDS.lwlockSessions));
          ctx.reason("Sampled waits: LWLock/Buffer/IPC " + fmtPct(share * 100, 0) + " of waiting sessions, p95 " + fmtNum(lwStats.p95, 1) + " sessions", "activity_locks.wait_event_sample_profile");
        }
      }
      const sampling = ctx.rows("activity_locks.pg_wait_sampling_profile");
      if (sampling.length) {
        const share = sumBy(sampling.filter((row) => lwlockTypes.includes(String(row.wait_event_type))), "sample_share_pct") || 0;
        score = maxScore(score, scalePair(share, THRESHOLDS.lwlockSharePct));
        ctx.reason("pg_wait_sampling: LWLock/Buffer/IPC hold " + fmtPct(share, 0) + " of samples", "activity_locks.pg_wait_sampling_profile");
      }
      const slru = ctx.rows("wal_io_checkpoints.slru_statistics");
      if (slru.length) {
        const low = slru.filter((row) => toNumber(row.hit_pct) !== null && toNumber(row.block_accesses) > 10000 && toNumber(row.hit_pct) < 95);
        if (low.length) {
          score = maxScore(score, 0.5);
          ctx.reason("SLRU caches with hit ratio below 95 %: " + low.map((row) => row.name + " " + fmtPct(toNumber(row.hit_pct), 1)).join(", "), "wal_io_checkpoints.slru_statistics");
        }
      }
      return score;
    },

    session_churn_raw(ctx) {
      let score = null;
      const pressure = ctx.rows("activity_locks.connection_pressure");
      if (pressure.length) {
        const used = toNumber(pressure[0].used_connections);
        if (used !== null) {
          score = maxScore(score, scalePair(used, THRESHOLDS.connectionsMany));
          ctx.reason(used + " connections in use (max_connections " + pressure[0].max_connections + ")", "activity_locks.connection_pressure");
          ctx.fact("Connections", String(used));
        }
      }
      const backends = seriesTotalStats(ctx, "snapshot_charts_db.database_backends");
      if (backends) {
        score = maxScore(score, scalePair(backends.p95, THRESHOLDS.connectionsMany));
        ctx.reason("Backends p95 " + fmtNum(backends.p95, 0) + " in the window", "snapshot_charts_db.database_backends");
      }
      const outcomes = ctx.rows("snapshot_delta_workload.database_session_outcomes_delta");
      const window = ctx.facts.windowSeconds();
      if (outcomes.length && window) {
        const sessions = sumBy(outcomes, "sessions_delta") || 0;
        const rate = sessions / window;
        score = maxScore(score, scalePair(rate, THRESHOLDS.sessionRate));
        ctx.reason(fmtNum(rate, 1) + " new sessions per second in the window (" + sessions + " total)", "snapshot_delta_workload.database_session_outcomes_delta");
        ctx.fact("Sessions per second", fmtNum(rate, 1));
      }
      return score;
    },

    memory_pressure(ctx) {
      const score = memoryPressure(ctx);
      return maxScore(score, logSignalScore(ctx, "memory"), findingsScore(ctx, {roles: ["support"], weightedOnly: true, excludeItems: MIXED_LOG_ITEMS}));
    }
  };

  // The memory pressure helper is shared with the damping of RAM causes.
  function memoryPressure(ctx) {
    return cachedEvaluation(ctx, "memoryPressure", memoryPressureRaw);
  }

  function memoryPressureRaw(ctx) {
      return maxScore(memoryAvailable(ctx), swapUsage(ctx));
  }

  function memoryAvailable(ctx) {
    return cachedEvaluation(ctx, "memoryAvailable", memoryAvailableRaw);
  }

  function memoryAvailableRaw(ctx) {
      let score = null;
      const memory = ctx.facts.memory();
      if (memory.total) {
        ctx.fact("RAM", fmtBytes(memory.total));
        if (memory.available !== null) {
          const availPct = (memory.available / memory.total) * 100;
          score = maxScore(score, scalePair(availPct, THRESHOLDS.memAvailablePct));
          ctx.reason("MemAvailable " + fmtBytes(memory.available) + " (" + fmtPct(availPct, 0) + " of RAM) at collection time", "os.memory_info");
        }
      }
      const used = seriesNamed(ctx, "snapshot_charts_os.os_memory_pressure", "RAM used");
      if (used) {
        const stats = seriesStats(used.values);
        if (stats) {
          score = maxScore(score, scalePair(stats.p95, THRESHOLDS.memUsedPct));
          ctx.reason("RAM used p95 " + fmtPct(stats.p95, 0) + " in the window", "snapshot_charts_os.os_memory_pressure");
        }
      }
      return score;
  }

  function swapUsage(ctx) {
    return cachedEvaluation(ctx, "swapUsage", swapUsageRaw);
  }

  function swapUsageRaw(ctx) {
      let score = null;
      const memory = ctx.facts.memory();
      if (memory.swapTotal && memory.swapFree !== null) {
        const swapUsedPct = ((memory.swapTotal - memory.swapFree) / memory.swapTotal) * 100;
        score = scalePair(swapUsedPct, THRESHOLDS.swapUsedPct);
        ctx.reason("Swap used " + fmtPct(swapUsedPct, 0) + " of " + fmtBytes(memory.swapTotal), "os.memory_info");
      } else if (memory.swapTotal === 0) {
        score = 0;
        ctx.fact("Swap", "none");
      }
      const swapSeries = ctx.series("snapshot_charts_os.os_memory_pressure").filter((series) => /^swap used$/i.test(series.name));
      for (const series of swapSeries) {
        const stats = seriesStats(series.values);
        if (stats) {
          score = maxScore(score, scalePair(stats.p95, THRESHOLDS.swapUsedPct));
          ctx.reason(series.name + " p95 " + fmtPct(stats.p95, 0), "snapshot_charts_os.os_memory_pressure");
        }
      }
      if (score !== null) ctx.reason("Swap occupancy does not establish active paging. Check swap-in/out rates before attributing current I/O waits to swap.");
      return score;
  }

  const causeEvaluators = {
    work_mem_budget_raw(ctx) {
      const workMem = ctx.facts.setting("work_mem");
      const maxConn = ctx.facts.setting("max_connections");
      const hashMult = ctx.facts.setting("hash_mem_multiplier");
      const memory = ctx.facts.memory();
      let score = null;
      if (workMem && workMem.value !== null) {
        ctx.fact("work_mem", fmtBytes(workMem.value));
        if (maxConn && maxConn.value !== null) {
          const budget = workMem.value * maxConn.value * 2;
          ctx.fact("work_mem x max_connections x 2", fmtBytes(budget));
          if (memory.total) {
            const ratio = budget / memory.total;
            score = maxScore(score, scalePair(ratio, THRESHOLDS.workMemRatio));
            ctx.reason("work_mem " + fmtBytes(workMem.value) + " x " + maxConn.value + " connections x 2 nodes = " + fmtBytes(budget) + " (" + fmtPct(ratio * 100, 0) + " of RAM)", "overview.pg_settings");
          }
        }
        if (hashMult && hashMult.value !== null) ctx.fact("hash_mem_multiplier", String(hashMult.raw));
      }
      const spills = ctx.rows("sql_workload.top_sql_by_temp_io").filter((row) => (toNumber(row.temp_io_bytes) || toNumber(row.temp_blks_written) || 0) > 0);
      if (spills.length) {
        score = maxScore(score, scalePair(spills.length, THRESHOLDS.spillingStatements) * 0.6);
        ctx.reason(spills.length + " statement(s) write temporary files", "sql_workload.top_sql_by_temp_io");
      }
      return score;
    },

    shared_buffers(ctx) {
      const sb = ctx.facts.setting("shared_buffers");
      const memory = ctx.facts.memory();
      let score = null;
      if (sb && sb.value !== null) {
        ctx.fact("shared_buffers", fmtBytes(sb.value));
        if (memory.total) {
          const pct = (sb.value / memory.total) * 100;
          score = maxScore(score, scalePair(pct, THRESHOLDS.sharedBuffersPct));
          if (pct < THRESHOLDS.sharedBuffersSmallPct) {
            score = maxScore(score, 0.3);
          }
          ctx.reason("shared_buffers is " + fmtPct(pct, 0) + " of RAM (25 % is the usual start, 60-80 % starves the page cache)", "overview.pg_settings");
        }
      }
      const used = seriesNamed(ctx, "buffer_cache.utilization", "used");
      const unused = seriesNamed(ctx, "buffer_cache.utilization", "unused");
      if (used && unused) {
        const usedStats = seriesStats(used.values);
        const unusedStats = seriesStats(unused.values);
        if (usedStats && unusedStats) {
          const total = usedStats.last + unusedStats.last;
          const usedPct = total > 0 ? (usedStats.last / total) * 100 : null;
          ctx.fact("shared_buffers in use", fmtPct(usedPct, 0));
          if (usedPct !== null && usedPct < 50) {
            ctx.reason("Only " + fmtPct(usedPct, 0) + " of shared_buffers is in use: the working set is smaller than the cache", "buffer_cache.utilization");
          }
        }
      }
      const counts = ctx.series("buffer_cache.usage_count_distribution");
      if (counts.length) {
        const hot = counts.filter((series) => /[3-5]/.test(series.name));
        const all = seriesStats(sumSeries(counts));
        const hotStats = hot.length ? seriesStats(sumSeries(hot)) : null;
        if (all && hotStats && all.last > 0) {
          const hotShare = hotStats.last / all.last;
          ctx.fact("Buffers with usage count >= 3", fmtPct(hotShare * 100, 0));
          if (hotShare > 0.8) {
            score = maxScore(score, 0.5);
            ctx.reason(fmtPct(hotShare * 100, 0) + " of buffers are hot (usage count >= 3): the working set exceeds shared_buffers", "buffer_cache.usage_count_distribution");
          }
        }
      }
      return score;
    },

    cache_efficiency(ctx) {
      let score = null;
      const hits = seriesByPrefix(ctx, "snapshot_charts_db.database_block_access_rate", "hit");
      const reads = seriesByPrefix(ctx, "snapshot_charts_db.database_block_access_rate", "read");
      if (hits.length && reads.length) {
        const hitStats = seriesStats(sumSeries(hits));
        const readStats = seriesStats(sumSeries(reads));
        if (hitStats && readStats && hitStats.mean + readStats.mean > 0) {
          const missPct = (readStats.mean / (hitStats.mean + readStats.mean)) * 100;
          score = maxScore(score, scalePair(missPct, THRESHOLDS.cacheMissPct));
          ctx.reason("Cache hit " + fmtPct(100 - missPct, 2) + " in the window (" + fmtNum(readStats.mean, 0) + " blocks/s read from the OS)", "snapshot_charts_db.database_block_access_rate");
          ctx.fact("Hit ratio (window)", fmtPct(100 - missPct, 2));
        }
      }
      const stats = ctx.rows("overview.database_stats").filter((row) => !/^template[01]$/.test(String(row.datname)));
      if (stats.length) {
        const hit = sumBy(stats, "blks_hit") || 0;
        const read = sumBy(stats, "blks_read") || 0;
        if (hit + read > 0) {
          const missPct = (read / (hit + read)) * 100;
          if (score === null) score = scalePair(missPct, THRESHOLDS.cacheMissPct);
          ctx.reason("Cumulative cache hit " + fmtPct(100 - missPct, 2) + " since stats reset", "overview.database_stats");
          ctx.fact("Hit ratio (cumulative)", fmtPct(100 - missPct, 2));
        }
      }
      const tables = ctx.rows("object_workload.table_io").filter((row) => (toNumber(row.total_blks_read) || 0) > 10000 && toNumber(row.cache_hit_pct) !== null && toNumber(row.cache_hit_pct) < 90);
      if (tables.length) {
        score = maxScore(score, 0.4);
        ctx.reason(tables.length + " table(s) with hit ratio below 90 %: " + tables.slice(0, 3).map((row) => row.schemaname + "." + row.relname + " " + fmtPct(toNumber(row.cache_hit_pct), 0)).join(", "), "object_workload.table_io");
      }
      return score;
    },

    huge_pages(ctx) {
      const hp = ctx.facts.hugePages();
      if (!hp) return null;
      let score = 0;
      const actual = String(hp.huge_pages_actual || "").toLowerCase();
      const shared = toNumber(hp.shared_memory_size_bytes) || toNumber(hp.shared_buffers_bytes) || 0;
      ctx.fact("huge_pages", String(hp.huge_pages_requested) + " -> " + String(hp.huge_pages_actual));
      ctx.fact("Shared memory", fmtBytes(shared));
      if (actual !== "on" && shared >= THRESHOLDS.hugePagesMinBytes) {
        score = Math.max(score, 0.6);
        ctx.reason("huge_pages are " + (actual || "unknown") + " with " + fmtBytes(shared) + " of shared memory: page tables grow and TLB misses cost CPU", "os.postgresql_huge_pages");
      }
      const thp = String(hp.transparent_huge_pages_mode || "").toLowerCase();
      if (thp) {
        ctx.fact("transparent_hugepage", thp);
        if (/always/.test(thp)) {
          score = Math.max(score, 0.6);
          ctx.reason("transparent_hugepage = always: khugepaged compaction stalls; set never or madvise", "os.postgresql_huge_pages");
        }
      }
      const pageTablesPct = toNumber(hp.host_page_tables_pct_ram);
      if (pageTablesPct !== null) {
        score = Math.max(score, scalePair(pageTablesPct, THRESHOLDS.pageTablesPct));
        ctx.fact("Page tables", fmtPct(pageTablesPct, 2) + " of RAM");
      }
      const shortfall = toNumber(hp.default_pool_shortfall_pages);
      if (shortfall !== null && shortfall > 0) {
        score = Math.max(score, 0.6);
        ctx.reason("Huge page pool is short by " + fmtNum(shortfall, 0) + " pages (vm.nr_hugepages)", "os.postgresql_huge_pages");
      }
      if (score === 0) ctx.reason("Huge page configuration matches the shared memory size");
      return score;
    },

    disk_saturation(ctx) {
      return diskSaturation(ctx).score;
    },

    disk_read(ctx) {
      return diskDirection(ctx, "read");
    },

    disk_write(ctx) {
      return diskDirection(ctx, "write");
    },

    read_queries(ctx) {
      let score = null;
      const rows = ctx.rows("sql_workload.top_sql_by_shared_io");
      if (rows.length) {
        const sum = sumBy(rows, "shared_blks_read") || 0;
        const top = topRows(rows, "shared_blks_read", 3);
        if (sum > 0 && top.length) {
          const share = top[0].value / sum;
          score = maxScore(score, scalePair(share, THRESHOLDS.topStatementShare) * 0.6);
          ctx.reason("Top statement reads " + fmtPct(share * 100, 0) + " of the listed shared blocks (query_id " + top[0].row.query_id + ", " + fmtBytes(top[0].value * 8192) + ")", "sql_workload.top_sql_by_shared_io");
        }
      }
      const delta = ctx.rows("snapshot_delta_workload.sql_io_delta");
      if (delta.length) {
        const top = topRows(delta, "shared_read_blks_per_sec", 3).filter((entry) => entry.value > 0);
        if (top.length) {
          ctx.reason("Readers in the window: " + top.map((entry) => "query_id " + entry.row.query_id + " " + fmtBytes(entry.value * 8192) + "/s").join(", "), "snapshot_delta_workload.sql_io_delta");
          score = maxScore(score, scale(top[0].value * 8192, 20 * 1024 ** 2, 200 * 1024 ** 2) * 0.6);
        }
      }
      const tables = topRows(ctx.rows("object_workload.table_io"), "total_blks_read", 3);
      if (tables.length) {
        ctx.fact("Most read tables", tables.map((entry) => entry.row.schemaname + "." + entry.row.relname).join(", "));
      }
      return shareScaled(ctx, score, "read", ["client backend"]);
    },

    io_autovacuum_reads(ctx) {
      return autovacuumIoShare(ctx, "read");
    },

    io_autovacuum_writes(ctx) {
      return autovacuumIoShare(ctx, "write");
    },

    backup_readers(ctx) {
      const activity = ctx.rows("backend_os.backend_activity");
      const tree = ctx.facts.processTree();
      const backup = activity.filter((row) => /pg_dump|pg_basebackup|pg_restore|pgbackrest|barman|wal-g/i.test(String(row.application_name || "")));
      const senders = tree.lines.filter((line) => line.kind === "walsender" && /backup/i.test(line.command));
      const replication = ctx.rows("replication.physical_replication").filter((row) => /backup/i.test(String(row.state || "")));
      const count = backup.length + senders.length + replication.length;
      if (!activity.length && !tree.lines.length && !replication.length) return null;
      if (count) {
        ctx.reason(count + " backup/dump session(s) running: " + backup.map((row) => row.application_name).concat(senders.map((line) => truncate(line.command, 40))).slice(0, 3).join(", "), backup.length ? "backend_os.backend_activity" : "backend_os.postgres_process_tree");
        return 0.4;
      }
      ctx.reason("No backup or dump session at collection time");
      return 0;
    },

    wal_volume(ctx) {
      let score = null;
      const rate = seriesTotalStats(ctx, "snapshot_charts_db.wal_growth_rate");
      if (rate) {
        score = maxScore(score, scalePair(rate.p95, THRESHOLDS.walBytesPerSec));
        ctx.reason("WAL " + fmtBytes(rate.mean) + "/s mean, " + fmtBytes(rate.p95) + "/s p95", "snapshot_charts_db.wal_growth_rate");
        ctx.fact("WAL rate p95", fmtBytes(rate.p95) + "/s");
      }
      const activity = ctx.rows("snapshot_delta_workload.wal_activity_delta");
      if (activity.length) {
        const records = toNumber(activity[0].wal_records_delta) || 0;
        const fpi = toNumber(activity[0].wal_fpi_delta) || 0;
        const full = toNumber(activity[0].wal_buffers_full_delta) || 0;
        if (records > 0) {
          const share = fpi / records;
          score = maxScore(score, scalePair(share, THRESHOLDS.fpiShare) * 0.6);
          ctx.reason("Full-page images per WAL record " + share.toFixed(2) + " in the window" + (full > 0 ? "; wal_buffers_full grew by " + fmtNum(full, 0) : ""), "snapshot_delta_workload.wal_activity_delta");
        }
        if (full > 0) score = maxScore(score, 0.3);
      } else {
        const stats = ctx.rows("wal_io_checkpoints.wal_statistics");
        if (stats.length) {
          const records = toNumber(stats[0].wal_records) || 0;
          const fpi = toNumber(stats[0].wal_fpi) || 0;
          if (records > 0) {
            const share = fpi / records;
            score = maxScore(score, scalePair(share, THRESHOLDS.fpiShare) * 0.6);
            ctx.reason("Full-page images per WAL record " + share.toFixed(2) + " since stats reset; " + fmtBytes(toNumber(stats[0].wal_bytes)) + " of WAL", "wal_io_checkpoints.wal_statistics");
          }
        }
      }
      const top = topRows(ctx.rows("sql_workload.top_sql_by_wal"), "wal_bytes", 3);
      if (top.length) {
        ctx.fact("Top WAL statements", top.map((entry) => "query_id " + entry.row.query_id + " " + fmtBytes(entry.value)).join(", "));
      }
      const durability = ctx.rows("overview.durability_safety_settings");
      for (const row of durability) {
        ctx.fact(String(row.setting_name), String(row.current_value));
      }
      return shareScaled(ctx, score, "write", ["walwriter", "wal"]);
    },

    checkpoints(ctx) {
      let score = null;
      const requested = seriesNamed(ctx, "snapshot_charts_db.checkpoint_trigger_events", "requested");
      const timedSeries = seriesNamed(ctx, "snapshot_charts_db.checkpoint_trigger_events", "timed");
      const completed = seriesNamed(ctx, "snapshot_charts_db.checkpoint_trigger_events", "completed");
      if (requested && (timedSeries || completed)) {
        const req = seriesStats(requested.values) || {sum: 0};
        // "timed" counts timer-triggered checkpoints (including skipped ones); "completed"
        // (18+) counts every performed checkpoint, requested ones included.
        const timedSum = timedSeries ? (seriesStats(timedSeries.values) || {sum: 0}).sum : Math.max(0, (seriesStats(completed.values) || {sum: 0}).sum - req.sum);
        if (req.sum + timedSum > 0) {
          const share = req.sum / (req.sum + timedSum);
          score = maxScore(score, scalePair(share, THRESHOLDS.requestedCheckpointShare));
          ctx.reason(fmtNum(req.sum, 0) + " requested and " + fmtNum(timedSum, 0) + " timed checkpoints in the window (requested share " + fmtPct(share * 100, 0) + ")", "snapshot_charts_db.checkpoint_trigger_events");
        } else {
          ctx.reason("No checkpoint started in the window", "snapshot_charts_db.checkpoint_trigger_events");
          score = maxScore(score, 0);
        }
      } else {
        const checkpointer = ctx.rows("wal_io_checkpoints.checkpointer");
        const bgwriter = ctx.rows("wal_io_checkpoints.bgwriter");
        const row = checkpointer[0] || bgwriter[0];
        if (row) {
          const req = toNumber(row.num_requested === undefined ? row.checkpoints_req : row.num_requested);
          const tim = toNumber(row.num_timed === undefined ? row.checkpoints_timed : row.num_timed);
          if (req !== null && tim !== null && req + tim > 0) {
            const share = req / (req + tim);
            score = maxScore(score, scalePair(share, THRESHOLDS.requestedCheckpointShare));
            ctx.reason(fmtNum(req, 0) + " requested and " + fmtNum(tim, 0) + " timed checkpoints since stats reset (requested share " + fmtPct(share * 100, 0) + ")", checkpointer.length ? "wal_io_checkpoints.checkpointer" : "wal_io_checkpoints.bgwriter");
          }
        }
      }
      const log = ctx.rows("server_log.checkpoints");
      if (log.length) {
        const sync = maxBy(log, "sync_s");
        if (sync.value !== null) {
          score = maxScore(score, scalePair(sync.value, THRESHOLDS.checkpointSyncSec));
          ctx.reason("Longest checkpoint sync phase " + sync.value.toFixed(1) + " s in the log window", "server_log.checkpoints");
          ctx.fact("Max sync", sync.value.toFixed(1) + " s");
        }
        const reasons = {};
        for (const row of log) {
          const key = String(row.reason || "").trim();
          if (key) reasons[key] = (reasons[key] || 0) + (toNumber(row.repeat_count) || 1);
        }
        const keys = Object.keys(reasons);
        if (keys.length) ctx.fact("Checkpoint reasons", keys.map((key) => key + " x" + reasons[key]).join(", "));
      }
      const delta = ctx.rows("snapshot_delta_workload.checkpointer_delta");
      if (delta.length) {
        const done = toNumber(delta[0].checkpoints_done_delta);
        const syncMs = toNumber(delta[0].sync_time_ms_delta);
        if (done && syncMs !== null) {
          const perCheckpoint = syncMs / done / 1000;
          score = maxScore(score, scalePair(perCheckpoint, THRESHOLDS.checkpointSyncSec));
          ctx.reason("Sync time per completed checkpoint " + perCheckpoint.toFixed(2) + " s in the window", "snapshot_delta_workload.checkpointer_delta");
        }
      }
      return shareScaled(ctx, score, "write", ["checkpointer"]);
    },

    backend_writes(ctx) {
      let score = null;
      const writes = seriesByPrefix(ctx, "snapshot_charts_db.buffer_writes_by_process", "");
      if (writes.length) {
        const client = writes.filter((series) => /backend|client/i.test(series.name));
        const all = seriesStats(sumSeries(writes));
        const clientStats = client.length ? seriesStats(sumSeries(client)) : null;
        if (all && all.mean > 0) {
          const share = clientStats ? clientStats.mean / all.mean : 0;
          score = maxScore(score, scalePair(share, THRESHOLDS.clientWriteShare));
          ctx.reason("Client backends wrote " + fmtPct(share * 100, 0) + " of buffer bytes in the window (" + writes.map((series) => series.name + " " + fmtBytes(seriesStats(series.values).mean) + "/s").join(", ") + ")", "snapshot_charts_db.buffer_writes_by_process");
          ctx.fact("Backend write share", fmtPct(share * 100, 0));
        } else {
          ctx.reason("No buffer writes in the window", "snapshot_charts_db.buffer_writes_by_process");
        }
      }
      if (score === null) {
        const io = ctx.rows("wal_io_checkpoints.pg_stat_io").filter((row) => row.object === "relation");
        if (io.length) {
          const total = sumBy(io, "writes") || 0;
          const client = sumBy(io.filter((row) => row.backend_type === "client backend"), "writes") || 0;
          if (total > 0) {
            const share = client / total;
            score = maxScore(score, scalePair(share, THRESHOLDS.clientWriteShare));
            ctx.reason("Client backends did " + fmtPct(share * 100, 0) + " of relation writes since stats reset", "wal_io_checkpoints.pg_stat_io");
          }
          const fsyncs = sumBy(io.filter((row) => row.backend_type === "client backend"), "fsyncs") || 0;
          if (fsyncs > 0) {
            score = maxScore(score, 0.6);
            ctx.reason("Client backends performed " + fmtNum(fsyncs, 0) + " fsyncs: the checkpointer's fsync queue overflowed", "wal_io_checkpoints.pg_stat_io");
          }
        } else {
          const bg = ctx.rows("wal_io_checkpoints.bgwriter");
          if (bg.length && bg[0].buffers_backend !== undefined) {
            const backend = toNumber(bg[0].buffers_backend) || 0;
            const checkpoint = toNumber(bg[0].buffers_checkpoint) || 0;
            const clean = toNumber(bg[0].buffers_clean) || 0;
            const total = backend + checkpoint + clean;
            if (total > 0) {
              const share = backend / total;
              score = maxScore(score, scalePair(share, THRESHOLDS.clientWriteShare));
              ctx.reason("buffers_backend is " + fmtPct(share * 100, 0) + " of all buffer writes since stats reset", "wal_io_checkpoints.bgwriter");
            }
            if ((toNumber(bg[0].buffers_backend_fsync) || 0) > 0) {
              score = maxScore(score, 0.6);
              ctx.reason("buffers_backend_fsync > 0: backends had to fsync themselves", "wal_io_checkpoints.bgwriter");
            }
          }
        }
      }
      const delta = ctx.rows("snapshot_delta_workload.background_writer_delta");
      if (delta.length) {
        const backend = toNumber(delta[0].buffers_backend_delta);
        const clean = toNumber(delta[0].buffers_clean_delta) || 0;
        const fsync = toNumber(delta[0].buffers_backend_fsync_delta) || 0;
        const maxwritten = toNumber(delta[0].maxwritten_clean_delta) || 0;
        if (backend !== null) ctx.fact("Backend buffer writes (window)", fmtNum(backend, 0) + " vs bgwriter " + fmtNum(clean, 0));
        if (fsync > 0) {
          score = maxScore(score, 0.6);
          ctx.reason("Backends fsynced " + fmtNum(fsync, 0) + " times in the window", "snapshot_delta_workload.background_writer_delta");
        }
        if (maxwritten > 0) {
          score = maxScore(score, 0.3);
          ctx.reason("bgwriter hit bgwriter_lru_maxpages " + fmtNum(maxwritten, 0) + " times: it cannot keep up", "snapshot_delta_workload.background_writer_delta");
        }
      }
      const pressure = ctx.series("snapshot_charts_db.writer_pressure_events");
      if (pressure.length) {
        const stats = seriesStats(sumSeries(pressure));
        if (stats && stats.sum > 0) {
          score = maxScore(score, 0.4);
          ctx.reason(fmtNum(stats.sum, 0) + " writer pressure events in the window", "snapshot_charts_db.writer_pressure_events");
        }
      }
      return score;
    },

    temp_files(ctx) {
      let score = null;
      const rate = seriesTotalStats(ctx, "snapshot_charts_db.database_temp_bytes_rate");
      if (rate) {
        score = maxScore(score, scalePair(rate.p95, THRESHOLDS.tempBytesPerSec));
        ctx.reason("Temporary files " + fmtBytes(rate.mean) + "/s mean, " + fmtBytes(rate.p95) + "/s p95", "snapshot_charts_db.database_temp_bytes_rate");
      } else {
        const delta = ctx.rows("snapshot_delta_workload.database_workload_delta");
        const perSec = sumBy(delta, "temp_bytes_per_sec");
        if (perSec !== null) {
          score = maxScore(score, scalePair(perSec, THRESHOLDS.tempBytesPerSec));
          ctx.reason("Temporary files " + fmtBytes(perSec) + "/s in the window", "snapshot_delta_workload.database_workload_delta");
        }
      }
      const spills = ctx.rows("sql_workload.top_sql_by_temp_io").filter((row) => (toNumber(row.temp_io_bytes) || toNumber(row.temp_blks_written) || 0) > 0);
      if (spills.length) {
        score = maxScore(score, scalePair(spills.length, THRESHOLDS.spillingStatements) * 0.6);
        const top = topRows(spills, "temp_io_bytes", 3);
        ctx.reason(spills.length + " statement(s) spill to disk; largest: " + top.map((entry) => "query_id " + entry.row.query_id + " " + fmtBytes(entry.value)).join(", "), "sql_workload.top_sql_by_temp_io");
      }
      const stats = ctx.rows("overview.database_stats");
      if (stats.length) {
        const bytes = sumBy(stats, "temp_bytes");
        const files = sumBy(stats, "temp_files");
        if (bytes !== null) ctx.fact("Temp bytes since reset", fmtBytes(bytes) + " in " + fmtNum(files || 0, 0) + " files");
      }
      return score === null ? null : maxScore(score, 0);
    },

    dml_volume(ctx) {
      let score = null;
      const rate = seriesTotalStats(ctx, "snapshot_charts_db.tables_top_dml_rate") || seriesTotalStats(ctx, "snapshot_charts_db.database_tuple_dml_rate");
      if (rate) {
        score = maxScore(score, scalePair(rate.p95, THRESHOLDS.dmlRowsPerSec) * 0.6);
        ctx.reason("DML " + fmtNum(rate.mean, 0) + " rows/s mean, " + fmtNum(rate.p95, 0) + " rows/s p95", "snapshot_charts_db.tables_top_dml_rate");
        ctx.fact("DML rows/s p95", fmtNum(rate.p95, 0));
      }
      const rows = ctx.rows("object_workload.table_workload");
      if (rows.length) {
        const top = topRows(rows, "total_dml", 3);
        if (top.length) ctx.fact("Most mutated tables", top.map((entry) => entry.row.schemaname + "." + entry.row.relname).join(", "));
        const lowHot = rows.filter((row) => (toNumber(row.n_tup_upd) || 0) > 100000)
          .map((row) => ({name: row.schemaname + "." + row.relname, hot: ((toNumber(row.n_tup_hot_upd) || 0) / (toNumber(row.n_tup_upd) || 1)) * 100}))
          .filter((entry) => entry.hot < THRESHOLDS.hotSharePct[0]);
        if (lowHot.length) {
          const worst = lowHot.sort((a, b) => a.hot - b.hot)[0];
          score = maxScore(score, scalePair(worst.hot, THRESHOLDS.hotSharePct) * 0.6);
          ctx.reason(lowHot.length + " update-heavy table(s) with HOT share below " + THRESHOLDS.hotSharePct[0] + " %: " + lowHot.slice(0, 3).map((entry) => entry.name + " " + fmtPct(entry.hot, 0)).join(", ") + " (fillfactor, indexed columns)", "object_workload.table_workload");
        }
      }
      const dirtied = topRows(ctx.rows("sql_workload.top_sql_by_shared_io"), "shared_blks_dirtied", 2);
      if (dirtied.length && dirtied[0].value > 0) {
        ctx.fact("Top dirtying statement", "query_id " + dirtied[0].row.query_id + " " + fmtBytes(dirtied[0].value * 8192));
      }
      return score;
    },

    disk_space(ctx) {
      let score = null;
      const usage = ctx.rows("os.disk_usage");
      if (usage.length) {
        const worst = maxBy(usage, "used_pct");
        if (worst.value !== null) {
          score = maxScore(score, scalePair(worst.value, THRESHOLDS.diskUsedPct));
          ctx.reason("Fullest filesystem " + worst.row.mount_point + " at " + fmtPct(worst.value, 0) + " (" + fmtBytes(toNumber(worst.row.available_bytes)) + " free)", "os.disk_usage");
          ctx.fact("Fullest filesystem", worst.row.mount_point + " " + fmtPct(worst.value, 0));
        }
      }
      const slots = ctx.rows("replication.replication_slots");
      const retained = sumBy(slots, "retained_wal_bytes");
      if (retained !== null && retained > 0) {
        score = maxScore(score, scalePair(retained, THRESHOLDS.retainedWalBytes));
        ctx.reason("Replication slots retain " + fmtBytes(retained) + " of WAL", "replication.replication_slots");
      }
      const archiver = ctx.rows("wal_io_checkpoints.wal_archiver");
      if (archiver.length) {
        const ahead = toNumber(archiver[0].segments_ahead_of_last_archived_same_timeline);
        if (ahead !== null && ahead > 0) {
          score = maxScore(score, scalePair(ahead, THRESHOLDS.archiveLagSegments));
          ctx.reason(fmtNum(ahead, 0) + " WAL segments wait for the archiver", "wal_io_checkpoints.wal_archiver");
        }
      }
      const logs = ctx.rows("server_log.log_files_overview");
      const logBytes = sumBy(logs, "size_bytes");
      if (logBytes !== null) {
        score = maxScore(score, scalePair(logBytes, THRESHOLDS.logBytes));
        ctx.fact("Log files", fmtBytes(logBytes) + " in " + logs.length + " files");
      }
      score = maxScore(score, logSignalScore(ctx, "space"), findingsScore(ctx, {roles: ["support"], weightedOnly: true, excludeItems: MIXED_LOG_ITEMS}));
      return score;
    },

    bloat(ctx) {
      return bloatScore(ctx);
    },

    log_errors(ctx) {
      const chronology = ctx.rows("server_log.error_chronology");
      const top = ctx.rows("server_log.top_errors");
      let score = ctx.anyCollected() ? 0 : null;
      const observations = [];
      for (const [itemId, rows, severityColumn, countColumn] of [
        ["server_log.error_chronology", chronology, "severity", "repeat_count"],
        ["server_log.top_errors", top, "severity_worst", "occurrences"]
      ]) {
        if (!rows.length) continue;
        const count = rows.reduce((total, row) => total + (toNumber(row[countColumn]) || 1), 0);
        const severities = [...new Set(rows.map((row) => String(row[severityColumn] || "").toUpperCase()))];
        if (severities.includes("PANIC")) score = 1;
        else if (severities.includes("FATAL")) score = maxScore(score, THRESHOLDS.fatalLogScore);
        observations.push(count);
        ctx.reason(ctx.title(itemId) + ": " + count + " listed error occurrences (" + severities.join(", ") + "; counts may be lower bounds)", itemId);
      }
      const terminations = seriesTotalStats(ctx, "server_log.query_termination_events");
      if (terminations && terminations.sum > 0) {
        observations.push(terminations.sum);
        score = maxScore(score, THRESHOLDS.terminationLogScore);
        ctx.fact("Query terminations", fmtNum(terminations.sum, 0));
        ctx.reason(fmtNum(terminations.sum, 0) + " statement/lock timeouts or cancellations in the log window", "server_log.query_termination_events");
      }
      // All sources overlap and have independent caps. Without event identities,
      // their maximum is a safe lower bound; their sum would double-count events.
      const occurrences = Math.max(0, ...observations);
      const window = ctx.logWindowMinutes();
      if (occurrences > 0) {
        ctx.fact("Observed log events (lower bound)", String(occurrences));
        if (window) {
          score = maxScore(score, scalePair(occurrences / window, THRESHOLDS.errorsPerMinute));
          ctx.reason("Observed log event rate at least " + (occurrences / window).toFixed(2) + " per minute; overlapping sources are not added");
        } else {
          score = maxScore(score, 0.3);
        }
      }
      const worst = topRows(top, "occurrences", 3);
      if (worst.length) {
        ctx.reason("Most frequent: " + worst.map((entry) => truncate(entry.row.message_sample, 70) + " x" + fmtNum(entry.value, 0)).join(" | "), "server_log.top_errors");
      }
      return score;
    },

    crashes(ctx) {
      let score = maxScore(findingsScore(ctx, {excludeItems: MIXED_LOG_ITEMS}), logSignalScore(ctx, "crash"));
      const control = ctx.rows("overview.pg_controldata");
      const state = control.find((row) => /cluster state/i.test(String(row.parameter)));
      if (state) ctx.fact("Cluster state", String(state.value));
      if (score === null && ctx.anyCollected()) {
        ctx.reason("No crash, checksum or corruption evidence");
        return 0;
      }
      return score;
    },

    wraparound(ctx) {
      let score = null;
      const databases = ctx.rows("storage_vacuum.database_wraparound");
      if (databases.length) {
        const worst = maxBy(databases, "xid_age");
        if (worst.value !== null) {
          const share = worst.value / XID_LIMIT;
          score = maxScore(score, scalePair(share, THRESHOLDS.xidAgeShare));
          const trigger = toNumber(worst.row.xid_freeze_trigger_pct);
          ctx.reason("Oldest database XID age " + fmtNum(worst.value, 0) + " (" + fmtPct(share * 100, 1) + " of the 2^31 limit" + (trigger !== null ? ", " + fmtPct(trigger, 0) + " of autovacuum_freeze_max_age" : "") + ") in " + worst.row.datname, "storage_vacuum.database_wraparound");
          ctx.fact("Max XID age", fmtNum(worst.value, 0));
          if (trigger !== null && trigger >= 100) {
            score = maxScore(score, 0.5);
          }
        }
        const mx = maxBy(databases, "multixact_age");
        if (mx.value !== null) {
          score = maxScore(score, scalePair(mx.value / XID_LIMIT, THRESHOLDS.xidAgeShare));
          ctx.fact("Max multixact age", fmtNum(mx.value, 0));
        }
      }
      const sequences = ctx.rows("storage_vacuum.sequence_status").filter((row) => row.exhaustion_applicable !== false);
      if (sequences.length) {
        const worst = maxBy(sequences, "percent");
        if (worst.value !== null) {
          score = maxScore(score, scalePair(worst.value, THRESHOLDS.sequencePct));
          if (worst.value >= THRESHOLDS.sequencePct[0] * 0.5) {
            ctx.reason("Sequence " + worst.row.sequence_name + " consumed " + fmtPct(worst.value, 1) + " of its range", "storage_vacuum.sequence_status");
          }
          ctx.fact("Most consumed sequence", worst.row.sequence_name + " " + fmtPct(worst.value, 1));
        }
      }
      const pressure = ctx.rows("server_log.wraparound_pressure");
      if (pressure.length) {
        score = maxScore(score, 1);
        ctx.reason(pressure.length + " wraparound warning(s) in the server log", "server_log.wraparound_pressure");
      }
      const queue = ctx.rows("storage_vacuum.autovacuum_queue").filter((row) => row.wraparound_vacuum_due === true);
      if (queue.length) {
        score = maxScore(score, 0.4);
        ctx.reason(queue.length + " table(s) due for an anti-wraparound vacuum", "storage_vacuum.autovacuum_queue");
      }
      return score;
    },

    vacuum_lag(ctx) {
      let score = null;
      const queue = ctx.rows("storage_vacuum.autovacuum_queue");
      if (queue.length) {
        const due = queue.filter((row) => row.dead_tuple_vacuum_due === true || row.insert_vacuum_due === true);
        const overdue = maxBy(queue, "dead_tuple_overdue_factor");
        if (overdue.value !== null) {
          score = maxScore(score, scalePair(overdue.value, THRESHOLDS.vacuumOverdueFactor));
        }
        score = maxScore(score, scalePair(due.length, [3, 15]) * 0.6);
        ctx.reason(due.length + " table(s) past their autovacuum threshold" + (overdue.value !== null && overdue.value >= 1 ? "; worst " + overdue.row.schemaname + "." + overdue.row.relname + " at " + overdue.value.toFixed(1) + "x the threshold" : ""), "storage_vacuum.autovacuum_queue");
        const dead = queue.filter((row) => (toNumber(row.n_live_tup) || 0) + (toNumber(row.n_dead_tup) || 0) > THRESHOLDS.deadTupleMinRows)
          .map((row) => ({name: row.schemaname + "." + row.relname, pct: ((toNumber(row.n_dead_tup) || 0) / ((toNumber(row.n_live_tup) || 0) + (toNumber(row.n_dead_tup) || 0))) * 100}))
          .sort((a, b) => b.pct - a.pct);
        if (dead.length && dead[0].pct >= THRESHOLDS.deadTuplePct[0]) {
          score = maxScore(score, scalePair(dead[0].pct, THRESHOLDS.deadTuplePct));
          ctx.reason("Dead tuple share: " + dead.slice(0, 3).map((entry) => entry.name + " " + fmtPct(entry.pct, 0)).join(", "), "storage_vacuum.autovacuum_queue");
        }
        const running = queue.filter((row) => row.vacuum_in_progress === true).length;
        if (running) ctx.fact("Tables being vacuumed", String(running));
      }
      score = maxScore(score, bloatScore(ctx));
      const events = ctx.rows("server_log.maintenance_events");
      if (events.length) {
        score = maxScore(score, 0.5);
        ctx.reason(events.length + " heavy or failed maintenance event(s) in the log window", "server_log.maintenance_events");
      }
      return score;
    },

    xmin_horizon(ctx) {
      let score = null;
      const horizon = ctx.rows("storage_vacuum.xmin_horizon");
      if (horizon.length) {
        const age = toNumber(horizon[0].data_horizon_age_tx);
        if (age !== null) {
          score = maxScore(score, scalePair(age, THRESHOLDS.horizonAgeTx));
          ctx.reason("Data xmin horizon is " + fmtNum(age, 0) + " transactions behind", "storage_vacuum.xmin_horizon");
          ctx.fact("Horizon age", fmtNum(age, 0) + " tx");
        }
      }
      const blockers = ctx.rows("storage_vacuum.xmin_horizon_blockers");
      for (const row of blockers) {
        const age = toNumber(row.age_tx);
        if (age !== null) {
          score = maxScore(score, scalePair(age, THRESHOLDS.horizonAgeTx));
          ctx.reason("Blocker " + row.component + (row.blocker_pid ? " pid " + row.blocker_pid : "") + (row.slot_name ? " slot " + row.slot_name : "") + (row.prepared_gid ? " gid " + row.prepared_gid : "") + ": " + fmtNum(age, 0) + " tx", "storage_vacuum.xmin_horizon_blockers");
        }
      }
      const long = maxBy(ctx.rows("activity_locks.long_transactions"), "xact_age_seconds");
      if (long.value !== null) {
        score = maxScore(score, scalePair(long.value, THRESHOLDS.longTransactionSec));
        ctx.reason("Longest open transaction " + fmtSeconds(long.value) + " (pid " + long.row.pid + ", " + long.row.state + ")", "activity_locks.long_transactions");
      }
      const idle = maxBy(ctx.rows("activity_locks.idle_in_transaction"), "idle_seconds");
      if (idle.value !== null) {
        score = maxScore(score, scalePair(idle.value, THRESHOLDS.idleInTransactionSec));
        ctx.reason("Longest idle in transaction " + fmtSeconds(idle.value) + " (pid " + idle.row.pid + ")", "activity_locks.idle_in_transaction");
      }
      const prepared = maxBy(ctx.rows("storage_vacuum.prepared_xacts"), "prepared_age_seconds");
      if (prepared.value !== null) {
        score = maxScore(score, scalePair(prepared.value, THRESHOLDS.preparedAgeSec));
        ctx.reason("Prepared transaction " + prepared.row.gid + " open for " + fmtSeconds(prepared.value), "storage_vacuum.prepared_xacts");
      }
      const slot = maxBy(ctx.rows("replication.replication_slots"), "xmin_age");
      if (slot.value !== null) {
        score = maxScore(score, scalePair(slot.value, THRESHOLDS.slotXminAge));
        ctx.reason("Slot " + slot.row.slot_name + " holds xmin " + fmtNum(slot.value, 0) + " transactions old", "replication.replication_slots");
      }
      return score;
    },

    locks(ctx) {
      let score = null;
      const waits = ctx.rows("activity_locks.lock_waits");
      if (waits.length) {
        const longest = maxBy(waits, "blocked_ms");
        score = maxScore(score, scalePair(waits.length, THRESHOLDS.blockedSessions), longest.value === null ? null : scalePair(longest.value, THRESHOLDS.lockWaitMs));
        ctx.reason(waits.length + " blocked session(s)" + (longest.value !== null ? ", longest wait " + fmtSeconds(longest.value / 1000) + " on " + longest.row.blocked_locktype + " " + truncate(longest.row.blocked_target, 40) + " held by pid " + longest.row.blocker_pid + " (" + longest.row.blocker_state + ")" : ""), "activity_locks.lock_waits");
      }
      const tree = ctx.rows("activity_locks.blocking_lock_tree");
      if (tree.length) {
        const roots = tree.filter((row) => row.is_root === true);
        const worst = maxBy(roots, "root_blocked_sessions");
        if (worst.value !== null) {
          score = maxScore(score, scalePair(worst.value, THRESHOLDS.blockedSessions));
          ctx.reason("Root blocker pid " + worst.row.pid + " (" + worst.row.state + ") holds " + fmtNum(worst.value, 0) + " session(s)", "activity_locks.blocking_lock_tree");
        }
      }
      const logWaits = ctx.rows("server_log.lock_waits");
      if (logWaits.length) {
        const longest = maxBy(logWaits, "wait_ms");
        if (longest.value !== null) {
          score = maxScore(score, scalePair(longest.value, THRESHOLDS.lockWaitMs) * 0.8);
          ctx.reason(logWaits.length + " lock wait(s) in the log window, longest " + fmtSeconds(longest.value / 1000), "server_log.lock_waits");
        }
      }
      const deadlocks = ctx.rows("server_log.deadlock_events");
      const deadlockCount = deadlocks.reduce((acc, row) => acc + (toNumber(row.repeat_count) || 1), 0);
      const chart = seriesTotalStats(ctx, "snapshot_charts_db.database_deadlocks");
      const delta = sumBy(ctx.rows("snapshot_delta_workload.database_workload_delta"), "deadlocks_delta");
      // Both measure pg_stat_database.deadlocks over overlapping windows.
      // Keep the larger observation (partial series may miss events), never add.
      const windowDeadlocks = Math.max(chart ? chart.sum : 0, delta || 0);
      const windowSource = delta !== null && (!chart || delta >= chart.sum)
        ? "snapshot_delta_workload.database_workload_delta" : "snapshot_charts_db.database_deadlocks";
      if (deadlockCount > 0 || windowDeadlocks > 0) {
        score = maxScore(score, scale(Math.max(deadlockCount, windowDeadlocks), 1, 10) * 0.4 + 0.6);
        if (deadlockCount > 0) ctx.reason(deadlockCount + " deadlock(s) in the log window", "server_log.deadlock_events");
        if (windowDeadlocks > 0) ctx.reason(windowDeadlocks + " deadlock(s) in the snapshot window (overlapping chart and endpoint counts are not added)", windowSource);
      }
      const terminations = ctx.series("server_log.query_termination_events");
      if (terminations.length) {
        const stats = seriesStats(sumSeries(terminations));
        if (stats && stats.sum > 0) {
          score = maxScore(score, 0.4);
          ctx.reason(fmtNum(stats.sum, 0) + " statement/lock timeouts or cancellations in the log window", "server_log.query_termination_events");
        }
      }
      if (score === null && ctx.anyCollected()) {
        ctx.reason("No lock waits or deadlocks observed");
        return 0;
      }
      return score;
    },

    connections(ctx) {
      let score = null;
      const pressure = ctx.rows("activity_locks.connection_pressure");
      if (pressure.length) {
        const row = pressure[0];
        const usedPct = toNumber(row.used_pct);
        if (usedPct !== null) {
          score = maxScore(score, scalePair(usedPct, THRESHOLDS.connectionsUsedPct));
          ctx.reason(fmtNum(toNumber(row.used_connections), 0) + " of " + row.max_connections + " connections used (" + fmtPct(usedPct, 0) + "), " + fmtNum(toNumber(row.idle_in_transaction_connections), 0) + " idle in transaction, " + fmtNum(toNumber(row.waiting_connections), 0) + " waiting", "activity_locks.connection_pressure");
          ctx.fact("Connections used", fmtPct(usedPct, 0));
        }
      }
      const usage = ctx.rows("users_roles.session_usage");
      const worst = maxBy(usage, "limit_utilization_pct");
      if (worst.value !== null) {
        score = maxScore(score, scalePair(worst.value, THRESHOLDS.connectionsUsedPct));
        if (worst.value >= THRESHOLDS.connectionsUsedPct[0]) {
          ctx.reason("Role " + worst.row.role_name + " uses " + fmtPct(worst.value, 0) + " of its connection limit", "users_roles.session_usage");
        }
      }
      const outcomes = ctx.rows("snapshot_delta_workload.database_session_outcomes_delta");
      if (outcomes.length) {
        const fatal = (sumBy(outcomes, "sessions_fatal_delta") || 0) + (sumBy(outcomes, "sessions_killed_delta") || 0);
        const abandoned = sumBy(outcomes, "sessions_abandoned_delta") || 0;
        if (fatal > 0) {
          score = maxScore(score, 0.6);
          ctx.reason(fmtNum(fatal, 0) + " session(s) ended fatally or were killed in the window", "snapshot_delta_workload.database_session_outcomes_delta");
        }
        if (abandoned > 0) {
          score = maxScore(score, 0.3);
          ctx.reason(fmtNum(abandoned, 0) + " session(s) abandoned by clients in the window", "snapshot_delta_workload.database_session_outcomes_delta");
        }
      }
      return score;
    },

    replication(ctx) {
      let score = null;
      const senders = ctx.rows("replication.physical_replication");
      for (const row of senders) {
        const lagBytes = toNumber(row.current_to_replay_lag_bytes);
        const lagSec = toNumber(row.replay_lag_seconds);
        score = maxScore(score, lagBytes === null ? null : scalePair(lagBytes, THRESHOLDS.replayLagBytes), lagSec === null ? null : scalePair(lagSec, THRESHOLDS.replayLagSec));
        if (String(row.state) !== "streaming") score = maxScore(score, 0.6);
        ctx.reason("Standby " + (row.application_name || row.client_addr) + ": " + row.state + ", replay lag " + fmtBytes(lagBytes) + (lagSec !== null ? " / " + fmtSeconds(lagSec) : ""), "replication.physical_replication");
      }
      const receiver = ctx.rows("replication.wal_receiver");
      for (const row of receiver) {
        if (String(row.status) !== "streaming") {
          score = maxScore(score, 0.6);
          ctx.reason("WAL receiver status " + row.status, "replication.wal_receiver");
        }
        const lag = toNumber(row.receive_lag_bytes);
        if (lag !== null) score = maxScore(score, scalePair(lag, THRESHOLDS.replayLagBytes));
      }
      const standby = ctx.rows("replication.standby_recovery_state");
      if (standby.length && standby[0].in_recovery === true) {
        const lag = toNumber(standby[0].receive_replay_lag_bytes);
        const since = toNumber(standby[0].seconds_since_last_replayed_xact);
        score = maxScore(score, lag === null ? null : scalePair(lag, THRESHOLDS.replayLagBytes));
        // Transaction age grows on an idle, fully caught-up standby too.
        // It is not a lag measurement without unapplied WAL at the same time.
        if (lag > 0 && since !== null) score = maxScore(score, scalePair(since, THRESHOLDS.replayLagSec));
        ctx.reason("This server is a standby: receive-to-replay lag " + fmtBytes(lag) + (since !== null ? ", last replayed transaction " + fmtSeconds(since) + " ago" : "") + (standby[0].replay_paused === true ? ", replay PAUSED" : ""), "replication.standby_recovery_state");
        if (since !== null && !(lag > 0)) ctx.reason("Last transaction age alone does not prove replay lag; the primary may be idle", "replication.standby_recovery_state");
        if (standby[0].replay_paused === true) score = maxScore(score, 0.6);
      }
      const slots = ctx.rows("replication.replication_slots");
      for (const row of slots) {
        const status = String(row.wal_status || "");
        const retained = toNumber(row.retained_wal_bytes);
        if (status === "lost") score = maxScore(score, 1);
        else if (status === "unreserved") score = maxScore(score, 0.6);
        if (row.active === false && retained !== null) {
          score = maxScore(score, scalePair(retained, THRESHOLDS.retainedWalBytes));
          ctx.reason("Inactive slot " + row.slot_name + " retains " + fmtBytes(retained) + (status ? " (" + status + ")" : ""), "replication.replication_slots");
        }
      }
      const sync = ctx.rows("replication.synchronous_replication_status");
      if (sync.length) {
        const row = sync[0];
        if (row.quorum_satisfied === false) {
          score = maxScore(score, 1);
          ctx.reason("Synchronous replication quorum is not satisfied: commits wait", "replication.synchronous_replication_status");
        }
        const waiting = toNumber(row.syncrep_waiting_sessions);
        if (waiting !== null && waiting > 0) {
          score = maxScore(score, 0.6);
          ctx.reason(fmtNum(waiting, 0) + " session(s) waiting in SyncRep", "replication.synchronous_replication_status");
        }
      }
      const capacity = maxBy(ctx.rows("replication.replication_capacity"), "utilization_pct");
      if (capacity.value !== null) {
        score = maxScore(score, scalePair(capacity.value, THRESHOLDS.capacityPct));
        if (capacity.value >= THRESHOLDS.capacityPct[0]) {
          ctx.reason(capacity.row.resource + " at " + fmtPct(capacity.value, 0) + " of its limit", "replication.replication_capacity");
        }
      }
      const conflicts = sumBy(ctx.rows("snapshot_delta_workload.standby_recovery_conflicts_delta"), "conflicts_total_delta");
      if (conflicts !== null && conflicts > 0) {
        score = maxScore(score, 0.6);
        ctx.reason(fmtNum(conflicts, 0) + " recovery conflict(s) in the window", "snapshot_delta_workload.standby_recovery_conflicts_delta");
      }
      const subs = ctx.rows("replication.subscription_workers");
      const errors = (sumBy(subs, "apply_error_count") || 0) + (sumBy(subs, "sync_error_count") || 0);
      if (errors > 0) {
        score = maxScore(score, 0.6);
        ctx.reason(fmtNum(errors, 0) + " logical replication error(s)", "replication.subscription_workers");
      }
      const delay = seriesTotalStats(ctx, "snapshot_charts_db.standby_replay_delay");
      const lagSeries = ctx.series("snapshot_charts_db.standby_replay_lag_bytes");
      const lagStats = lagSeries.length ? seriesStats(sumSeries(lagSeries)) : null;
      if (lagStats) {
        score = maxScore(score, scalePair(lagStats.p95, THRESHOLDS.replayLagBytes));
        ctx.reason("Standby unapplied WAL p95 " + fmtBytes(lagStats.p95), "snapshot_charts_db.standby_replay_lag_bytes");
      }
      if (delay) {
        ctx.fact("Last replayed transaction age p95", fmtSeconds(delay.p95));
        const lagAt = new Map();
        for (const series of lagSeries) {
          series.values.forEach((value, index) => {
            const time = series.times[index];
            if (time && isFiniteNumber(value)) lagAt.set(time, Math.max(lagAt.get(time) || 0, value));
          });
        }
        const delayed = ctx.series("snapshot_charts_db.standby_replay_delay").flatMap((series) =>
          series.values.filter((value, index) => isFiniteNumber(value) && lagAt.get(series.times[index]) > 0));
        const correlated = delayed.length >= 2 ? seriesStats(delayed) : null;
        if (correlated) {
          score = maxScore(score, scalePair(correlated.p95, THRESHOLDS.replayLagSec));
          ctx.reason("Replay age p95 " + fmtSeconds(correlated.p95) + " while the same samples show unapplied WAL", "snapshot_charts_db.standby_replay_delay");
        } else {
          ctx.reason("Replay age is informational without matching samples of unapplied WAL; an idle primary also makes it grow", "snapshot_charts_db.standby_replay_delay");
        }
      }
      score = maxScore(score, findingsScore(ctx, {roles: ["support"], weightedOnly: true}));
      if (score === null && ctx.anyCollected()) {
        if (delay || (standby.length && standby[0].in_recovery === true)) return null;
        if (!senders.length && !receiver.length && !slots.length) ctx.reason("No physical replication configured");
        return 0;
      }
      return score;
    },

    archiving(ctx) {
      const rows = ctx.rows("wal_io_checkpoints.wal_archiver");
      let score = null;
      if (rows.length) {
        const row = rows[0];
        ctx.fact("archive_mode", String(row.archive_mode));
        if (String(row.archive_mode) !== "off") {
          const failed = toNumber(row.failed_count) || 0;
          const ahead = toNumber(row.segments_ahead_of_last_archived_same_timeline);
          const lastFailed = Date.parse(row.last_failed_time || "");
          const lastArchived = Date.parse(row.last_archived_time || "");
          score = 0;
          if (failed > 0 && (!Number.isFinite(lastArchived) || lastFailed > lastArchived)) {
            score = 1;
            ctx.reason("archive_command is failing: last failure " + row.last_failed_time + " on " + row.last_failed_wal, "wal_io_checkpoints.wal_archiver");
          } else if (failed > 0) {
            score = 0.3;
            ctx.reason(fmtNum(failed, 0) + " archive failure(s) since stats reset, archiving recovered", "wal_io_checkpoints.wal_archiver");
          }
          if (ahead !== null) {
            score = Math.max(score, scalePair(ahead, THRESHOLDS.archiveLagSegments));
            ctx.reason(fmtNum(ahead, 0) + " segment(s) ahead of the last archived WAL", "wal_io_checkpoints.wal_archiver");
          }
        } else {
          ctx.reason("archive_mode = off: no WAL archiving");
          score = 0;
        }
      }
      const delta = ctx.rows("snapshot_delta_workload.wal_archiver_delta");
      if (delta.length && (toNumber(delta[0].failed_count_delta) || 0) > 0) {
        score = maxScore(score, 1);
        ctx.reason(fmtNum(toNumber(delta[0].failed_count_delta), 0) + " archive failure(s) in the window", "snapshot_delta_workload.wal_archiver_delta");
      }
      return maxScore(score, findingsScore(ctx, {roles: ["support"], weightedOnly: true}));
    },

    configuration(ctx) {
      let score = findingsScore(ctx);
      const eol = ctx.rows("overview.version_eol_status");
      if (eol.length) {
        const days = toNumber(eol[0].days_to_eol);
        if (days !== null) {
          score = maxScore(score, scalePair(days, THRESHOLDS.eolDays));
          ctx.reason("PostgreSQL " + eol[0].server_version + ": " + (days < 0 ? "end of life " + fmtNum(-days, 0) + " days ago" : fmtNum(days, 0) + " days to end of life"), "overview.version_eol_status");
          ctx.fact("Days to EOL", fmtNum(days, 0));
        }
      }
      for (const row of ctx.rows("overview.durability_safety_settings")) {
        const name = String(row.setting_name);
        const value = String(row.current_value).toLowerCase();
        ctx.fact(name, value);
        if (name === "fsync" && value === "off") {
          score = maxScore(score, 1);
          ctx.reason("fsync = off: a crash can corrupt the cluster", "overview.durability_safety_settings");
        } else if (name === "full_page_writes" && value === "off") {
          score = maxScore(score, 0.6);
          ctx.reason("full_page_writes = off: torn pages after a power loss are unrecoverable unless storage guarantees atomic 8 KB writes", "overview.durability_safety_settings");
        } else if (name === "synchronous_commit" && value === "off") {
          score = maxScore(score, 0.3);
          ctx.reason("synchronous_commit = off cluster-wide: the last commits are lost on a crash", "overview.durability_safety_settings");
        }
      }
      const pending = ctx.rows("cluster_inventory.pending_restart_settings");
      if (pending.length) {
        ctx.reason(pending.length + " setting(s) wait for a restart: " + pending.slice(0, 4).map((row) => row.name).join(", "), "cluster_inventory.pending_restart_settings");
      }
      const errors = ctx.rows("cluster_inventory.configuration_file_errors").filter((row) => row.error);
      if (errors.length) {
        ctx.reason(errors.length + " configuration entr(ies) the server cannot apply", "cluster_inventory.configuration_file_errors");
      }
      return score;
    },

    observability(ctx) {
      let score = null;
      const gaps = [];
      const notes = [];
      // Capability rows carry recommendation = "ok" when nothing is wrong; a missing or
      // unloaded extension weighs more than a tuning remark.
      const check = (itemId, label, weight) => {
        const rows = ctx.rows(itemId);
        if (!rows.length) return;
        const problems = rows.filter((row) => String(row.recommendation || "ok").trim().toLowerCase() !== "ok");
        const blocking = problems.filter((row) => /^(extension_available|extension_installed|preloaded|view_available|function_available|profile_view_available|required_view_columns)$/.test(String(row.capability)) && /^(false|off|no|none|0)$/i.test(String(row.value).trim()));
        if (blocking.length) {
          gaps.push(label + " (" + blocking.map((row) => row.capability).slice(0, 2).join(", ") + ")");
          score = maxScore(score, weight);
        } else {
          score = maxScore(score, problems.length ? 0.15 : 0);
          for (const row of problems.slice(0, 2)) notes.push(label + ": " + row.capability + " = " + row.value + " (" + truncate(row.recommendation, 80) + ")");
        }
      };
      check("sql_workload.pg_stat_statements_capabilities", "pg_stat_statements", 0.6);
      check("sql_workload.pg_stat_kcache_capabilities", "pg_stat_kcache", 0.3);
      check("activity_locks.pg_wait_sampling_capabilities", "pg_wait_sampling", 0.3);
      for (const note of notes) ctx.reason(note);
      const functions = ctx.rows("object_workload.function_workload");
      if (functions.length && functions.every((row) => String(row.track_functions) === "none")) {
        gaps.push("track_functions = none");
        score = maxScore(score, 0.3);
      }
      if (gaps.length) ctx.reason("Missing or disabled: " + gaps.join("; "), "sql_workload.pg_stat_statements_capabilities");
      else if (score !== null) ctx.reason("Statement, kernel and wait sampling diagnostics are available");
      return score;
    },

    maintenance_running(ctx) {
      const items = ["maintenance_progress.vacuum_progress", "maintenance_progress.create_index_progress", "maintenance_progress.cluster_progress", "maintenance_progress.copy_progress"];
      let count = 0;
      let score = null;
      for (const itemId of items) {
        const rows = ctx.rows(itemId);
        if (!rows.length) continue;
        count += rows.length;
        score = maxScore(score, 0.15);
        const age = maxBy(rows, "query_age_seconds");
        if (age.value !== null) {
          score = maxScore(score, scalePair(age.value, THRESHOLDS.maintenanceAgeSec));
        }
        if (rows.some((row) => row.anti_wraparound === true)) score = maxScore(score, 0.6);
        ctx.reason(rows.length + " " + ctx.title(itemId).replace(/ Progress$/, "").toLowerCase() + " operation(s)" + (age.value !== null ? ", longest " + fmtSeconds(age.value) : ""), itemId);
      }
      if (count === 0 && ctx.anyCollected()) {
        ctx.reason("No maintenance operation in progress");
        return 0;
      }
      return score;
    }
  };

  // ----------------------------------------- pressure damping and registry

  // Resource pressure in [0, 1] or null when the resource has no data.
  function pressureOf(ctx, kind) {
    if (kind === "cpu_user") return cpuComponent(ctx, ["user", "nice"], THRESHOLDS.cpuBusyPct, "User CPU");
    if (kind === "cpu_system") return cpuComponent(ctx, ["system", "irq", "softirq"], THRESHOLDS.cpuSystemPct, "System CPU");
    if (kind === "cpu_iowait") return cpuComponent(ctx, ["iowait"], THRESHOLDS.cpuIowaitPct, "I/O wait");
    if (kind === "cpu") {
      if (ctx.shared.cpuPressure === undefined) {
        const busy = cpuBusyStats(ctx);
        ctx.shared.cpuPressure = busy ? scalePair(busy.p95, THRESHOLDS.cpuBusyPct) : null;
      }
      return ctx.shared.cpuPressure;
    }
    if (kind === "disk") return diskSaturation(ctx).score;
    if (kind === "ram") return memoryPressure(ctx);
    return null;
  }

  // A cause is a bottleneck only when its resource is under pressure: full weight at
  // pressure 1, 30 % at pressure 0, 50 % when the pressure is unknown (one-shot reports).
  function damp(ctx, score, kind) {
    // Declarative pressure is applied once, after the evaluator. In particular,
    // copies under I/O wait must not also be damped by unrelated CPU/disk pressure.
    if (ctx.node.pressure) return score;
    return dampByPressure(ctx, score, kind);
  }

  function dampByPressure(ctx, score, kind) {
    if (!isFiniteNumber(score)) return null;
    const pressure = pressureOf(ctx, kind);
    const factor = pressure === null ? 0.5 : 0.3 + 0.7 * pressure;
    if (pressure !== null && score >= 0.34) {
      ctx.fact("Resource pressure", {ok: "Low", warn: "Elevated", crit: "High"}[statusOf(pressure)]);
    }
    return score * factor;
  }

  function heavyQueries(ctx) { return causes.heavy_queries(ctx); }
  function seqScans(ctx) { return causes.seq_scans_raw(ctx); }
  function indexEfficiency(ctx) { return causes.index_efficiency_raw(ctx); }
  function lightQueries(ctx) { return causes.light_queries_raw(ctx); }
  function jitParallel(ctx) { return causes.jit_parallel_raw(ctx); }
  function contention(ctx) { return causes.contention_raw(ctx); }
  function sessionChurn(ctx) { return causes.session_churn_raw(ctx); }
  function networkTraffic(ctx) { return causes.network_traffic_raw(ctx); }
  function workMemBudget(ctx) { return causeEvaluators.work_mem_budget_raw(ctx); }

  evaluators.system_time = causes.system_time;
  evaluators.memory_pressure = causes.memory_pressure;
  for (const [name, fn] of Object.entries(causeEvaluators)) {
    if (name.endsWith("_raw")) continue;
    if (["read_queries", "wal_volume", "checkpoints", "backend_writes", "temp_files", "dml_volume"].includes(name)) {
      evaluators[name] = (ctx) => damp(ctx, fn(ctx), "disk");
    } else {
      evaluators[name] = fn;
    }
  }

  // --------------------------------------------- shared evaluator helpers

  function cpuComponent(ctx, names, thresholds, label) {
    const parts = ctx.series("snapshot_charts_os.os_cpu_utilization").filter((series) => names.includes(series.name.toLowerCase()));
    // Require the main counter. Supplementary nice/irq counters alone cannot
    // establish that user/system time was low when the main series is missing.
    if (!parts.some((series) => series.name.toLowerCase() === names[0])) return null;
    const totals = parts[0].times.map((time) => {
      let value = 0;
      for (const part of parts) {
        const index = part.times.indexOf(time);
        if (index < 0 || !isFiniteNumber(part.values[index])) return null;
        value += part.values[index];
      }
      return value;
    });
    const stats = seriesStats(totals);
    if (!stats) return null;
    ctx.fact(label + " p95", fmtPct(stats.p95, 0));
    ctx.reason(label + " p95 " + fmtPct(stats.p95, 0) + ", mean " + fmtPct(stats.mean, 0), "snapshot_charts_os.os_cpu_utilization");
    return scalePair(stats.p95, thresholds);
  }

  function diskSaturation(ctx) {
    return cachedEvaluation(ctx, "diskSaturation", diskSaturationRaw);
  }

  function diskSaturationRaw(ctx) {
    let score = null;
    const devices = [];
    for (const series of seriesByPrefix(ctx, "snapshot_charts_os.os_disk_latency", "await")) {
      const match = /\(([^)]+)\)/.exec(series.name);
      const device = match ? match[1] : series.name;
      const stats = seriesStats(series.values);
      if (!stats) continue;
      const media = ctx.facts.mediaFor(device);
      const thresholds = THRESHOLDS.diskLatencyMs[media] || THRESHOLDS.diskLatencyMs.unknown;
      const deviceScore = scalePair(stats.p95, thresholds);
      score = maxScore(score, deviceScore);
      devices.push({device, media, p95: stats.p95, mean: stats.mean, score: deviceScore});
    }
    for (const series of seriesByPrefix(ctx, "snapshot_charts_os.os_disk_utilization", "util")) {
      const match = /\(([^)]+)\)/.exec(series.name);
      const device = match ? match[1] : series.name;
      const stats = seriesStats(series.values);
      if (!stats) continue;
      const media = ctx.facts.mediaFor(device);
      const utilScore = scalePair(stats.p95, THRESHOLDS.diskUtilPct) * (media === "hdd" ? 1 : 0.4);
      score = maxScore(score, utilScore);
      const entry = devices.find((candidate) => candidate.device === device);
      if (entry) entry.util = stats.p95;
      else devices.push({device, media, util: stats.p95, score: utilScore});
    }
    if (devices.length) {
      ctx.reason(devices.map((entry) => entry.device + " (" + entry.media + "): await p95 " + (entry.p95 === undefined ? "n/a" : entry.p95.toFixed(1) + " ms") + (entry.util === undefined ? "" : ", util p95 " + fmtPct(entry.util, 0))).join("; "), "snapshot_charts_os.os_disk_latency");
      const worst = devices.slice().sort((a, b) => (b.score || 0) - (a.score || 0))[0];
      ctx.fact("Worst device", worst.device + " " + worst.media);
    }
    const ioWaits = ctx.rows("activity_locks.wait_events").filter((row) => String(row.wait_event_type) === "IO");
    const ioSessions = sumBy(ioWaits, "sessions") || 0;
    if (ioSessions > 0) {
      score = maxScore(score, scale(ioSessions, 3, 20) * 0.6);
      ctx.reason(ioSessions + " session(s) waiting on I/O at collection time", "activity_locks.wait_events");
    }
    const ioTime = seriesTotalStats(ctx, "snapshot_charts_db.database_io_time_rate");
    if (ioTime) ctx.fact("PostgreSQL I/O time", fmtNum(ioTime.mean, 0) + " ms/s");
    const result = {score, devices};
    return result;
  }

  // Share of bytes per backend type from the pg_stat_io based chart or table, for one direction.
  function ioShares(ctx, direction) {
    const key = "ioShares_" + direction;
    if (ctx.shared[key]) return ctx.shared[key];
    const shares = {};
    let total = 0;
    let source = null;
    const chart = seriesByPrefix(ctx, "snapshot_charts_db.io_read_write_rate", direction + " (");
    if (chart.length) {
      for (const series of chart) {
        const match = /\(([^)]+)\)/.exec(series.name);
        const stats = seriesStats(series.values);
        if (!match || !stats) continue;
        shares[match[1]] = stats.mean;
        total += stats.mean;
      }
      source = "snapshot_charts_db.io_read_write_rate";
    } else {
      const rows = ctx.rows("snapshot_delta_workload.postgresql_io_delta");
      const column = direction === "read" ? "read_bytes_delta" : "write_bytes_delta";
      const fallback = direction === "read" ? "reads_delta" : "writes_delta";
      if (rows.length) {
        for (const row of rows) {
          const value = toNumber(row[column]) !== null ? toNumber(row[column]) : (toNumber(row[fallback]) || 0) * 8192;
          shares[row.backend_type] = (shares[row.backend_type] || 0) + value;
          total += value;
        }
        source = "snapshot_delta_workload.postgresql_io_delta";
      } else {
        const io = ctx.rows("wal_io_checkpoints.pg_stat_io");
        const col = direction === "read" ? "reads" : "writes";
        const bytesCol = direction === "read" ? "read_bytes" : "write_bytes";
        for (const row of io) {
          const value = toNumber(row[bytesCol]) !== null ? toNumber(row[bytesCol]) : (toNumber(row[col]) || 0) * 8192;
          shares[row.backend_type] = (shares[row.backend_type] || 0) + value;
          total += value;
        }
        if (io.length) source = "wal_io_checkpoints.pg_stat_io";
      }
    }
    const result = {shares, total, source};
    ctx.shared[key] = result;
    return result;
  }

  function diskDirection(ctx, direction) {
    const saturation = diskSaturation(ctx);
    const os = seriesTotalStats(ctx, direction === "read" ? "snapshot_charts_os.os_disk_read_throughput" : "snapshot_charts_os.os_disk_write_throughput");
    const other = seriesTotalStats(ctx, direction === "read" ? "snapshot_charts_os.os_disk_write_throughput" : "snapshot_charts_os.os_disk_read_throughput");
    let share = null;
    if (os) {
      ctx.fact("Host " + direction + " throughput", fmtBytes(os.mean) + "/s mean, " + fmtBytes(os.p95) + "/s p95");
      if (other && os.mean + other.mean > 0) share = os.mean / (os.mean + other.mean);
    }
    const io = ioShares(ctx, direction);
    if (io.total > 0) {
      const parts = Object.entries(io.shares).sort((a, b) => b[1] - a[1]).slice(0, 4)
        .map(([type, value]) => type + " " + fmtPct((value / io.total) * 100, 0));
      ctx.reason("PostgreSQL " + direction + "s by process: " + parts.join(", "), io.source);
    }
    if (share !== null) {
      ctx.reason(fmtPct(share * 100, 0) + " of host disk bytes are " + direction + "s", direction === "read" ? "snapshot_charts_os.os_disk_read_throughput" : "snapshot_charts_os.os_disk_write_throughput");
      ctx.fact(direction + " share", fmtPct(share * 100, 0));
    }
    const pressure = ctx.node.pressure ? pressureOf(ctx, ctx.node.pressure) : saturation.score;
    // Throughput proves activity, not health. Unknown latency/pressure stays grey.
    if (pressure === null) return null;
    if (!os && io.total <= 0) return null;
    return pressure * (share === null ? 0.5 : share);
  }

  // Scale a cause node's own score by its process share of the parent direction.
  function shareScaled(ctx, ownScore, direction, backendTypes) {
    const io = ioShares(ctx, direction);
    if (io.total > 0) {
      let bytes = 0;
      for (const [type, value] of Object.entries(io.shares)) {
        if (backendTypes.some((candidate) => type.toLowerCase().includes(candidate))) bytes += value;
      }
      const share = bytes / io.total;
      ctx.fact(direction + " share of " + backendTypes[0], fmtPct(share * 100, 0));
      const saturation = ctx.node.pressure ? pressureOf(ctx, ctx.node.pressure) : diskSaturation(ctx).score;
      if (saturation !== null) {
        return maxScore(ownScore, saturation * share);
      }
    }
    return ownScore;
  }

  function autovacuumIoShare(ctx, direction) {
    const io = ioShares(ctx, direction);
    if (io.total <= 0) {
      const runs = ctx.rows("server_log.autovacuum_runs");
      if (runs.length) {
        ctx.fact("Autovacuum runs in log window", String(runs.length));
        return 0;
      }
      return null;
    }
    let bytes = 0;
    for (const [type, value] of Object.entries(io.shares)) {
      if (/autovacuum/i.test(type)) bytes += value;
    }
    const share = bytes / io.total;
    ctx.reason("Autovacuum workers do " + fmtPct(share * 100, 0) + " of PostgreSQL " + direction + " bytes", io.source);
    ctx.fact("Autovacuum " + direction + " share", fmtPct(share * 100, 0));
    return damp(ctx, scalePair(share, THRESHOLDS.autovacuumIoShare), "disk");
  }

  function bloatScore(ctx) {
    return cachedEvaluation(ctx, "bloat", bloatScoreRaw);
  }

  function bloatScoreRaw(ctx) {
    let score = null;
    for (const [itemId, kind] of [["storage_vacuum.table_bloat_candidates", "table"], ["storage_vacuum.index_bloat_candidates", "index"]]) {
      const rows = ctx.rows(itemId).filter((row) => row.can_estimate !== false && (toNumber(row.wasted_bytes) || 0) >= THRESHOLDS.bloatMinWastedBytes);
      if (!rows.length) continue;
      const worst = maxBy(rows, "bloat_percent");
      const wasted = sumBy(rows, "wasted_bytes") || 0;
      if (worst.value !== null) {
        score = maxScore(score, scalePair(worst.value, THRESHOLDS.bloatPct));
        ctx.reason(rows.length + " bloated " + kind + "(s) wasting " + fmtBytes(wasted) + "; worst " + (worst.row.schema_name + "." + (worst.row.table_name || worst.row.index_name)) + " at " + fmtPct(worst.value, 0), itemId);
      }
    }
    const large = ctx.rows("indexes.large_indexes");
    if (large.length) {
      ctx.fact("Indexes larger than half their table", String(large.length));
    }
    if (score === null && ["storage_vacuum.table_bloat_candidates", "storage_vacuum.index_bloat_candidates"].some((itemId) => ["present", "empty"].includes(ctx.presence(itemId)))) {
      ctx.reason("No table or index wastes more than " + fmtBytes(THRESHOLDS.bloatMinWastedBytes) + " by the bloat estimate");
      score = 0;
    }
    return score;
  }

  // ------------------------------------------------------------- traversal

  const HINTS = {
    snapshots: "Run pg-diag in snapshots mode (--run-mode snapshots) to sample charts, rates and deltas for this node.",
    host: "Collect in local or remote (SSH) mode: remote-db-only mode has no access to the host.",
    log: "Add --log-depth-time-min N to include server log evidence.",
    pg_stat_statements: "Install and preload pg_stat_statements to see per-statement evidence.",
    pg_stat_kcache: "Install pg_stat_kcache for kernel CPU and filesystem I/O per statement.",
    pg_wait_sampling: "Install pg_wait_sampling for a continuous wait-event profile.",
    pg_buffercache: "Install pg_buffercache to see shared_buffers occupancy."
  };

  function requirementUnmet(requirement, runtime, node, presenceOf) {
    if (requirement === "snapshots") return runtime.mode !== "snapshots";
    if (requirement === "host") return runtime.collection_mode === "remote-db-only";
    if (requirement === "log") {
      const logItems = node.bindings.filter((binding) => binding.id.startsWith("server_log."));
      return logItems.length > 0 && logItems.every((binding) => ["absent", "skipped", "unsupported"].includes(presenceOf(binding.id)));
    }
    return null; // extension requirements are judged from item presence below
  }

  function buildHints(node, runtime, presenceOf, itemOf) {
    const hints = [];
    const seen = new Set();
    const push = (text) => {
      if (text && !seen.has(text)) {
        seen.add(text);
        hints.push(text);
      }
    };
    for (const requirement of node.requires || []) {
      const unmet = requirementUnmet(requirement, runtime, node, presenceOf);
      if (unmet === true) push(HINTS[requirement]);
      if (unmet === null) {
        const scoped = node.bindings.filter((binding) => binding.role !== "fact");
        if (scoped.length && scoped.every((binding) => ["absent", "skipped", "unsupported", "empty"].includes(presenceOf(binding.id)))) push(HINTS[requirement]);
      }
    }
    // Mode hints only when the whole category is missing from the node: a single absent
    // item next to present ones is a catalog difference, not a missing mode.
    const categoryOf = (itemId) => {
      if (itemId.startsWith("snapshot_") || itemId.startsWith("buffer_cache.") || itemId.endsWith("wait_event_sample_profile") || itemId.startsWith("backend_os.backend_proc")) return "snapshots";
      if (itemId.startsWith("os.") || itemId.startsWith("backend_os.")) return "host";
      if (itemId.startsWith("server_log.")) return "log";
      return null;
    };
    const categories = {};
    for (const binding of node.bindings) {
      const category = categoryOf(binding.id);
      if (!category) continue;
      const entry = categories[category] || (categories[category] = {collected: false, missing: false});
      const presence = presenceOf(binding.id);
      if (presence === "present" || presence === "empty") entry.collected = true;
      if (presence === "absent" || presence === "skipped") entry.missing = true;
    }
    if (categories.snapshots && !categories.snapshots.collected && categories.snapshots.missing && runtime.mode !== "snapshots") push(HINTS.snapshots);
    if (categories.host && !categories.host.collected && categories.host.missing && runtime.collection_mode === "remote-db-only") push(HINTS.host);
    if (categories.log && !categories.log.collected && categories.log.missing) push(HINTS.log);
    for (const binding of node.bindings) {
      const presence = presenceOf(binding.id);
      const item = itemOf(binding.id);
      if ((presence === "skipped" || presence === "unsupported" || presence === "error") && item && item.reason) {
        push(truncate(item.title || binding.id, 60) + ": " + truncate(item.reason, 160));
      }
    }
    return hints.slice(0, 5);
  }

  function evaluate(artifact, definition, options) {
    const opts = options || {};
    const items = (artifact && artifact.items) || {};
    const runtime = (artifact && artifact.runtime) || {};
    const definitionNodes = definition.nodes.map((node) => Object.assign({}, node, {bindings: node.bindings || [], requires: node.requires || []}));
    const byId = {};
    for (const node of definitionNodes) byId[node.id] = node;
    const children = {};
    for (const node of definitionNodes) {
      if (node.parent) {
        (children[node.parent] = children[node.parent] || []).push(node.id);
      }
    }
    const presenceCache = {};
    const presenceOf = (itemId) => {
      if (!(itemId in presenceCache)) presenceCache[itemId] = itemPresence(items[itemId]);
      return presenceCache[itemId];
    };
    const itemOf = (itemId) => items[itemId] || null;
    const shared = {};
    const evidencePool = (node) => {
      const scored = node.bindings.filter((binding) => binding.role !== "fact");
      return scored.length ? scored : node.bindings;
    };
    const logWindowMinutes = () => {
      const log = runtime.log_collection || {};
      const coverage = log.coverage || {};
      const from = Date.parse(String(coverage.covered_from || "").replace(" UTC", "Z").replace(" ", "T"));
      const to = Date.parse(String(coverage.covered_to || "").replace(" UTC", "Z").replace(" ", "T"));
      if (Number.isFinite(from) && Number.isFinite(to) && to > from) {
        return (to - from) / 60000;
      }
      const minutes = toNumber(coverage.requested_minutes) || toNumber(log.requested_minutes) || toNumber(runtime.log_depth_time_min);
      return minutes && minutes > 0 ? minutes : null;
    };

    const results = {};
    const evaluatorRegistry = Object.assign({}, evaluators, opts.evaluators || {});

    function evaluateNode(nodeId) {
      const node = byId[nodeId];
      const childIds = children[nodeId] || [];
      const childResults = childIds.map((childId) => evaluateNode(childId));
      const reasons = [];
      const facts = {};
      const evidence = [];
      const ctx = {
        node,
        runtime,
        shared,
        item: itemOf,
        presence: presenceOf,
        rows: (itemId) => tableRows(items[itemId]),
        series: (itemId) => chartSeries(items[itemId]),
        text: (itemId) => textOf(items[itemId]),
        title: (itemId) => (items[itemId] && items[itemId].title) || itemId,
        // Evidence pool: scored bindings, or every binding for facts-only nodes.
        anyPresent: () => evidencePool(node).some((binding) => presenceOf(binding.id) === "present"),
        anyCollected: () => evidencePool(node).some((binding) => ["present", "empty"].includes(presenceOf(binding.id))),
        reason: (text, itemId) => {
          if (text && !reasons.includes(text)) reasons.push(text);
          if (itemId && !evidence.includes(itemId)) evidence.push(itemId);
        },
        fact: (name, value) => {
          if (value !== null && value !== undefined && value !== "") facts[name] = String(value);
        },
        logWindowMinutes
      };
      ctx.facts = makeFacts(ctx);
      const evaluatorName = node.evaluator || "generic";
      const evaluator = evaluatorRegistry[evaluatorName];
      let ownScore = null;
      let error = null;
      if (typeof evaluator !== "function") {
        error = "unknown evaluator " + evaluatorName;
      } else if (evaluatorName === "aggregate") {
        ownScore = null;
      } else {
        // Collected but empty items are evidence too ("nothing found"); skipped, unsupported,
        // errored and absent items are not.
        const collected = evidencePool(node).some((binding) => ["present", "empty"].includes(presenceOf(binding.id)));
        if (collected) {
          try {
            let value = evaluator(ctx);
            if (node.pressure) value = dampByPressure(ctx, value, node.pressure);
            ownScore = isFiniteNumber(value) ? clamp01(value) : null;
          } catch (caught) {
            error = String(caught && caught.message ? caught.message : caught);
          }
        }
      }
      const childScore = maxScore(...childResults.map((child) => child.score));
      // Keep the measured own score separately, but never hide a critical child
      // behind a healthy parent: every finding must reach its root.
      const score = maxScore(ownScore, childScore);
      const bindings = node.bindings.map((binding) => {
        const item = itemOf(binding.id);
        return {
          id: binding.id,
          role: binding.role,
          presence: presenceOf(binding.id),
          title: item ? item.title || binding.id : binding.id,
          collection_status: item ? item.collection_status || null : null,
          section_id: item ? item.section_id || binding.id.split(".")[0] : binding.id.split(".")[0],
          rows: item && resultOf(item) && Array.isArray(resultOf(item).rows) ? resultOf(item).rows.length : null,
          kind: item && resultOf(item) ? resultOf(item).kind || null : null
        };
      });
      const result = {
        id: node.id,
        label: node.label,
        summary: node.summary || "",
        parent: node.parent || null,
        children: childIds,
        evaluator: evaluatorName,
        ownScore,
        childScore,
        score,
        ownStatus: statusOf(ownScore),
        status: statusOf(score),
        reasons,
        facts,
        evidence,
        error,
        bindings,
        present: bindings.filter((binding) => binding.presence === "present").length,
        scoredBindings: bindings.filter((binding) => binding.role !== "fact").length,
        hints: buildHints(node, runtime, presenceOf, itemOf),
        causes: [],
        causedBy: []
      };
      results[nodeId] = result;
      return result;
    }

    for (const rootId of definition.roots) {
      if (byId[rootId]) evaluateNode(rootId);
    }
    for (const link of definition.links || []) {
      if (results[link.from] && results[link.to]) {
        results[link.from].causes.push({to: link.to, label: link.label || ""});
        results[link.to].causedBy.push({from: link.from, label: link.label || ""});
      }
    }

    const order = [];
    const walk = (nodeId) => {
      order.push(nodeId);
      for (const childId of results[nodeId].children) walk(childId);
    };
    for (const rootId of definition.roots) if (results[rootId]) walk(rootId);

    const statusCounts = {ok: 0, warn: 0, crit: 0, no_data: 0};
    for (const nodeId of order) statusCounts[results[nodeId].status] += 1;
    const boundIds = new Set();
    for (const nodeId of order) for (const binding of results[nodeId].bindings) boundIds.add(binding.id);
    let presentItems = 0;
    for (const itemId of boundIds) if (presenceOf(itemId) === "present") presentItems += 1;
    const rootsWithData = definition.roots.filter((rootId) => results[rootId] && results[rootId].status !== STATUS.noData).length;

    return {
      version: VERSION,
      roots: definition.roots.filter((rootId) => results[rootId]),
      nodes: results,
      order,
      links: (definition.links || []).filter((link) => results[link.from] && results[link.to]),
      coverage: {
        runMode: runtime.mode || null,
        collectionMode: runtime.collection_mode || null,
        boundItems: boundIds.size,
        presentItems,
        artifactItems: Object.keys(items).length,
        rootsWithData,
        statusCounts,
        nodesWithoutData: order.filter((nodeId) => results[nodeId].status === STATUS.noData).length
      }
    };
  }

  return {
    VERSION,
    THRESHOLDS,
    STATUS,
    evaluate,
    evaluators,
    scale,
    statusOf,
    seriesStats,
    sumSeries,
    tableRows,
    chartSeries,
    textOf,
    itemPresence,
    decodeCell,
    classifyProcess,
    makeFacts,
    format: {pct: fmtPct, num: fmtNum, bytes: fmtBytes, seconds: fmtSeconds, truncate}
  };
});
