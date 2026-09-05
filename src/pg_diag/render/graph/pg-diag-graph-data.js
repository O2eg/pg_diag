/* pg_diag diagnostic graph data. No external dependencies. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.PgDiagGraphData = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const STATUS = {ok: "ok", warn: "warn", crit: "crit", noData: "no_data"};

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

  function seriesStats(values, minSamples = 1) {
    const finite = values.filter(isFiniteNumber);
    if (finite.length < minSamples) {
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

  // Independent events may sum the observed subset. Components of a total
  // require every component at that instant. Index alignment is legacy-only.
  function sumSeries(seriesList, {missing = "observed"} = {}) {
    if (!["strict", "observed"].includes(missing)) throw new Error("Unknown missing-value policy: " + missing);
    const timed = seriesList.some(series => Array.isArray(series.times));
    const rows = timed ? alignSeries(seriesList).map(row => row.values) :
      Array.from({length: Math.max(0, ...seriesList.map(series => series.values.length))},
        (_, index) => seriesList.map(series => series.values[index]));
    return rows.map(values => {
      const finite = values.filter(isFiniteNumber);
      if (!finite.length || missing === "strict" && finite.length !== values.length) return NaN;
      return finite.reduce((total, value) => total + value, 0);
    });
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
    const status = item.collection_status;
    if (["skipped", "unsupported", "error"].includes(status)) return status;
    if (status === "empty") return "empty";
    if (status !== "ok") return "error";
    const result = resultOf(item);
    if (!result) {
      return "empty";
    }
    if (result.kind === "table") {
      return Array.isArray(result.rows) && result.rows.length > 0 ? "present" : "empty";
    }
    if (result.kind === "chart") {
      return chartSeries(item).some((series) => series.finite >= minimumSamples(item)) ? "present" : "empty";
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
      windowSeconds(itemId) {
        return memo("windowSeconds:" + (itemId || "snapshot"), () => windowSeconds(ctx.runtime, itemId ? ctx.item(itemId) : null));
      }
    };
  }


  function observedZeros(ctx, itemId) {
    const item = ctx.item(itemId);
    const result = resultOf(item) || {};
    if (!item || !["present", "empty"].includes(ctx.presence(itemId)) ||
        (item.diagnostics || []).some(d => ["warning", "error"].includes(d.level))) return [];
    return (Array.isArray(result.zero_series) ? result.zero_series : []).filter(zero =>
      zero && typeof zero.name === "string" && Number.isInteger(zero.sample_count) &&
      zero.sample_count >= 2 && zero.missing_count === 0 &&
      (!Number.isInteger(result.sample_count) || zero.sample_count === result.sample_count));
  }

  function timestamp(value, offsetSeconds) {
    const text = String(value || "").replace(" UTC", "Z").replace(" ", "T");
    if (/(?:Z|[+-]\d{2}:?\d{2})$/i.test(text)) return Date.parse(text);
    // Log timestamps are server-local wall times. Never use the browser's zone.
    return isFiniteNumber(offsetSeconds) ? Date.parse(text + "Z") - offsetSeconds * 1000 : NaN;
  }

  function relationBlockSize(ctx) {
    const setting = ctx.facts.setting("block_size");
    const value = setting && (setting.value ?? toNumber(setting.raw));
    if (!(value > 0)) return null;
    ctx.fact("PostgreSQL block size", fmtBytes(value));
    return value;
  }

  function formatBlocks(ctx, blocks) {
    const size = relationBlockSize(ctx);
    return size ? fmtBytes(blocks * size) : fmtNum(blocks, 0) + " blocks";
  }

  function ioOperationBytes(row, bytesColumn, countColumn) {
    const bytes = toNumber(row[bytesColumn]);
    if (bytes !== null && bytes >= 0) return bytes;
    const count = toNumber(row[countColumn]);
    const size = toNumber(row.op_bytes);
    return count === 0 ? 0 : count > 0 && size > 0 ? count * size : null;
  }

  function lsnGap(end, start) {
    const parse = value => {
      const match = /^([0-9a-f]{1,8})\/([0-9a-f]{1,8})$/i.exec(String(value || ""));
      return match ? (BigInt("0x" + match[1]) << 32n) + BigInt("0x" + match[2]) : null;
    };
    const a = parse(end), b = parse(start);
    return a !== null && b !== null && a >= b ? Number(a - b) : null;
  }

  /** Status-aware view for evaluators. Raw decoders remain available for inspection. */
  function createAccess(items, onRead) {
    const read = (id, method) => {
      if (onRead) onRead(id, method);
      return items[id] || null;
    };
    const collected = item => item && ["ok", "empty"].includes(item.collection_status);
    const sampled = item => item && item.collection_status === "ok";
    return {
      item(id) {
        const item = read(id, "item");
        return collected(item) ? item : null;
      },
      presence: id => itemPresence(read(id, "presence")),
      rows(id) {
        const item = read(id, "rows");
        return sampled(item) ? tableRows(item) : [];
      },
      series(id) {
        const item = read(id, "series");
        return sampled(item) ? chartSeries(item).filter(series => series.finite >= minimumSamples(item)) : [];
      },
      text(id) {
        const item = read(id, "text");
        return sampled(item) ? textOf(item) : "";
      },
      minimumSamples: id => minimumSamples(read(id, "minimumSamples"))
    };
  }

  function minimumSamples(item) {
    const result = resultOf(item) || {};
    const chart = result.chart || {};
    if (["log_event", "query_event"].includes(chart.tooltip_kind)) return 1;
    // One interval is already a measured event count. Do not confuse a
    // count-valued gauge (sessions, buffers) with a counter delta. Older
    // artifacts may identify events by quantity or by a pre-normalized unit.
    const eventUnits = ["events", "deadlocks", "checkpoints", "restartpoints"];
    const series = result.series || [];
    const eventCounts = series.length > 0 && series.every(series => {
      const unit = series.unit || chart.unit;
      const quantity = series.quantity || chart.quantity;
      return eventUnits.includes(unit) || unit === "count" &&
        (series.semantic_role === "counter_delta" || eventUnits.includes(quantity));
    });
    return eventCounts ? 1 : 2;
  }

  /** Align UTC instants, including equivalent timestamps with different offsets. */
  function alignSeries(seriesList) {
    const times = new Set();
    const maps = seriesList.map(series => {
      const values = new Map();
      (series.times || []).forEach((time, index) => {
        const instant = timestamp(time, 0);
        if (Number.isFinite(instant)) {
          times.add(instant);
          // Duplicate coordinates cannot establish one unambiguous observation.
          values.set(instant, values.has(instant) ? NaN : series.values[index]);
        }
      });
      return values;
    });
    return [...times].sort((a, b) => a - b).map(time => ({
      time, values: maps.map(values => values.get(time) ?? NaN)
    }));
  }

  function windowSeconds(runtime, item) {
    const delta = (resultOf(item) || {}).delta_window;
    if (delta) {
      const seconds = toNumber(delta.duration_seconds);
      return seconds > 0 ? seconds : null;
    }
    const start = timestamp(runtime.snapshot_window_started_at || runtime.started_at, 0);
    const finish = timestamp(runtime.snapshot_window_finished_at || runtime.finished_at, 0);
    if (finish > start) return (finish - start) / 1000;
    const duration = toNumber(runtime.duration_seconds);
    return duration > 0 ? duration : null;
  }

  function logWindowMinutes(runtime) {
    const log = runtime.log_collection || {};
    const coverage = log.coverage || {};
    // Both bounds are in the server's log zone. Subtract wall times in the same
    // fixed zone rather than inheriting the browser's timezone/DST rules.
    const from = timestamp(coverage.covered_from, 0);
    const to = timestamp(coverage.covered_to, 0);
    if (to > from) return (to - from) / 60000;
    const minutes = toNumber(coverage.requested_minutes) || toNumber(log.requested_minutes) || toNumber(runtime.log_depth_time_min);
    return minutes > 0 ? minutes : null;
  }

  return {
    STATUS, isFiniteNumber, toNumber, clamp01, scale,
    scalePair, maxScore, statusOf, fmtPct, fmtNum,
    fmtBytes, fmtSeconds, truncate, sumBy, maxBy,
    topRows, seriesStats, sumSeries, decodeCell, resultOf,
    tableRows, hasColumn, chartSeries, textOf, itemPresence,
    classifyProcess, settingValue, makeFacts, observedZeros, timestamp,
    relationBlockSize, formatBlocks, ioOperationBytes, lsnGap, createAccess,
    minimumSamples, alignSeries, windowSeconds, logWindowMinutes
  };
});
