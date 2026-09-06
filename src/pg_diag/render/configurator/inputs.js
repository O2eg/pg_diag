/* Report-to-configurator inputs. No DOM, host access, or tuning formulas here. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PgDiagConfigurator = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const GiB = 1024 ** 3;
  const positive = (v) => v !== null && v !== undefined && v !== "" && typeof v !== "boolean"
    && Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : null;
  const bytes = (v) => String(Math.floor(v)); // Bare IEC amounts are bytes.
  const csv = (v) => '"' + String(v ?? "").replace(/"/g, '""') + '"';
  function rows(item) {
    if (!item || !["ok", "empty"].includes(item.collection_status) || item.result?.kind !== "table") return [];
    const columns = (item.result.columns || []).map(c => typeof c === "string" ? c : c.name);
    return (item.result.rows || []).map(row => Array.isArray(row)
      ? Object.fromEntries(columns.map((name, i) => [name, row[i]])) : row);
  }
  function text(item) {
    return item?.collection_status === "ok" && item.result?.kind === "plain_text"
      ? String(item.result.data ?? "") : "";
  }
  function cpuList(value) {
    if (!/^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$/.test(String(value).trim())) return null;
    const seen = new Set();
    for (const part of String(value).trim().split(",")) {
      const [a, b = a] = part.split("-").map(Number);
      if (a > b || b > 100000) return null;
      for (let i = a; i <= b; i++) seen.add(i);
    }
    return seen.size || null;
  }
  function diskType(row) {
    const value = [row.description, row.product, row.logicalname, row.filesystem, row.source,
      row.businfo, row.tran, row.transport, row.fstype, row.type].flat().join(" ");
    if (/\bnvme/i.test(value)) return "NVME";
    if (/\b(nfs\d?|cifs|ceph|glusterfs|iscsi|rbd)\b/i.test(value)) return "NETWORK";
    if (/\b(ssd|solid state)\b/i.test(value) || row.rota === false || row.rota === 0 || row.rota === "0") return "SSD";
    if (/\bsas\b/i.test(value)) return "SAS";
    if (/\b(sata|rotational|hard disk)\b/i.test(value) || row.rota === true || row.rota === 1 || row.rota === "1") return "SATA";
    return null;
  }
  function prepare(artifact) {
    const items = artifact?.items || {}, runtime = artifact?.runtime || {};
    const tables = new Map(Object.entries(items).map(([id, item]) => [id, rows(item)]));
    const inputs = {}, sources = [], notes = [], missing = [];
    const put = (field, value, itemIds, reason, confidence = "measured") => {
      inputs[field] = value;
      const previous = sources.findIndex(s => s.field === field);
      if (previous !== -1) sources.splice(previous, 1);
      sources.push({field, value, itemIds: [...new Set(itemIds)], reason, confidence});
    };
    const table = id => tables.get(id) || [];
    const settingsRows = table("overview.pg_settings");
    const settings = new Map(settingsRows.map(row => [row.setting_name ?? row.name, row]));
    const setting = name => settings.get(name)?.setting_value ?? settings.get(name)?.setting;
    const settingBytes = name => {
      const row = settings.get(name);
      return row?.unit_normalized === "bytes" ? positive(row.setting_normalized) : null;
    };
    // Retain every current setting, including extensions and settings the engine does not tune.
    const currentRows = [...settings].filter(([name, row]) => /^[a-zA-Z_][\w.]*$/.test(name)
      && (row.setting_value ?? row.setting) !== null && (row.setting_value ?? row.setting) !== undefined);
    const currentConfig = "name,setting,unit\n" + currentRows.map(([name, row]) =>
      [name, row.setting_value ?? row.setting, row.source_unit ?? row.unit ?? ""].map(csv).join(",")).join("\n") + "\n";
    if (!currentRows.length) missing.push("Current PostgreSQL settings");
    if (items["overview.pg_settings"]?.result?.truncated || settingsRows.some(r => r.result_truncated === true)
      || positive(items["overview.pg_settings"]?.result?.row_count) > settingsRows.length) {
      missing.push("Complete PostgreSQL settings (the collected table is truncated)");
    }

    // Read only database-host items. Collector runtime CPU/RAM are never a fallback.
    const cpuCandidates = [], ramCandidates = [], cpuLimits = [], ramLimits = [];
    for (const [id, data] of tables) {
      if (!id.startsWith("os.")) continue;
      for (const row of data) {
        for (const field of ["logical_cpus", "cpu_count", "online_cpus"])
          if (positive(row[field])) cpuCandidates.push({value: Number(row[field]), id});
        if (positive(row.total_ram_bytes)) ramCandidates.push({value: Number(row.total_ram_bytes), id});
        if (row.metric === "MemTotal" && row.unit_normalized === "bytes" && positive(row.value_normalized))
          ramCandidates.push({value: Number(row.value_normalized), id});
        // Explicit limits, when a content pack supplies them; never RSS or memory usage.
        for (const field of ["effective_cpu_cores", "cpu_limit_cores"])
          if (positive(row[field])) cpuLimits.push({value: Number(row[field]), id});
        if (positive(row.cpu_quota_us) && positive(row.cpu_period_us))
          cpuLimits.push({value: row.cpu_quota_us / row.cpu_period_us, id});
        const cpus = cpuList(row.cpuset_cpus_effective ?? "");
        if (cpus) cpuLimits.push({value: cpus, id});
        for (const field of ["effective_memory_bytes", "memory_limit_bytes"])
          if (positive(row[field]) && Number(row[field]) < 2 ** 60)
            ramLimits.push({value: Number(row[field]), id});
      }
    }
    const cpuText = text(items["os.cpu_info"]);
    const online = /(?:^|\n)\s*On-line CPU\(s\) list:\s*([^\n]+)/i.exec(cpuText);
    const count = /(?:^|\n)\s*CPU\(s\):\s*(\d+)/i.exec(cpuText);
    const parsedCpu = cpuList(online?.[1] ?? "") || positive(count?.[1]);
    if (parsedCpu) cpuCandidates.push({value: parsedCpu, id: "os.cpu_info"});
    if (!ramCandidates.length) {
      for (const row of table("os.lshw_memory")) {
        if (row.class === "memory" && /system memory/i.test(row.description || "") && positive(row.size))
          ramCandidates.push({value: Number(row.size), id: "os.lshw_memory"});
      }
    }
    const resource = (field, candidates, limits, label) => {
      const all = [...candidates, ...limits].sort((a, b) => a.value - b.value);
      if (!all.length) { missing.push(label); return; }
      const selected = all[0];
      put(field, field === "db_ram" ? bytes(selected.value) : String(selected.value), all.map(x => x.id),
        limits.length ? `${label}: minimum of host capacity and collected process/container limits.`
          : `${label}: host-visible capacity; process/container limits were not collected.`);
      if (new Set(candidates.map(c => c.value)).size > 1)
        notes.push(`${label} sources disagree; the smaller collected capacity is used.`);
    };
    resource("db_cpu", cpuCandidates, cpuLimits, "CPU capacity");
    resource("db_ram", ramCandidates, ramLimits, "RAM capacity");
    if ((!cpuLimits.length || !ramLimits.length) && /\boverlay\b|\bdocker\b|\blxc\b/i.test(
      text(items["os.mounts"]) + " " + table("os.disk_usage").map(r => r.filesystem).join(" "))) {
      notes.push("Container filesystem detected. CPU/RAM are host-visible where limits are absent; set the container allocation in Main → Hardware before using the proposed configuration.");
    }

    const directory = String(setting("data_directory") || "").replace(/\/+$/, "");
    const mounts = table("os.disk_usage");
    const mountFor = path => mounts.filter(r => typeof r.mount_point === "string" && path && (r.mount_point === "/"
      || path === r.mount_point || path.startsWith(r.mount_point.replace(/\/$/, "") + "/")))
      .sort((a, b) => b.mount_point.length - a.mount_point.length)[0];
    const mount = mountFor(directory);
    const devices = table("os.lshw_disk");
    const mountDetails = mount && table("os.disk_encryption_status").find(r =>
      r.mount_point === mount.mount_point && r.source === mount.filesystem);
    const mountPrefix = mount ? `${mount.filesystem} on ${mount.mount_point} type ` : "";
    const mountLine = mount && text(items["os.mounts"]).split("\n").find(line => line.startsWith(mountPrefix));
    const fstype = mountDetails?.fstype || (mountLine ? mountLine.slice(mountPrefix.length).split(" ")[0] : "");
    const mountedType = mount && (diskType({...mount, fstype}) || diskType(devices.find(r =>
      [r.logicalname].flat().some(name => {
        if (!name) return false;
        const device = String(name).startsWith("/dev/") ? String(name) : "/dev/" + name;
        const source = String(mount.filesystem);
        return source === device || (source.startsWith(device) && /^(?:p)?\d+$/.test(source.slice(device.length)));
      })) || {}));
    if (mountedType) put("db_disk_type", mountedType, ["os.disk_usage", ...(mountDetails ? ["os.disk_encryption_status"] : mountLine ? ["os.mounts"] : []), "os.lshw_disk"],
      `Storage backing data_directory: ${mount.filesystem} on ${mount.mount_point}.`);
    else {
      const types = [...new Set(devices.map(diskType).filter(Boolean))];
      if (types.length === 1 && devices.every(r => diskType(r))) {
        put("db_disk_type", types[0], ["os.lshw_disk"], "All inventoried disks have this class; data_directory could not be mapped to a physical device.", "inferred");
      } else missing.push("Database storage type (unambiguous device inventory or data_directory mount)");
    }

    const versionNum = positive(runtime.server_version_num) || positive(setting("server_version_num"));
    let major = versionNum ? String(Math.floor(versionNum / 10000)) : null;
    if (versionNum && versionNum < 100000) major = Math.floor(versionNum / 10000) + "." + Math.floor(versionNum / 100) % 100;
    if (!major) {
      const version = /PostgreSQL\s+(\d+)(?:\.(\d+))?/.exec(String(runtime.server_version || ""));
      if (version) major = Number(version[1]) >= 10 ? version[1] : version[1] + "." + version[2];
    }
    if (["9.6", "10", "11", "12", "13", "14", "15", "16", "17", "18"].includes(major))
      put("pg_version", major, ["overview.pg_settings"], "Collected server major version.");
    else missing.push("Supported PostgreSQL version (9.6 or 10–18)");
    const serverPlatform = text(items["os.kernel_version"]) + " " + String(runtime.server_version || "");
    if (/\bLinux\b/i.test(serverPlatform)) put("platform", "LINUX", ["os.kernel_version"], "Database server platform.");
    else if (/\b(Windows|mingw|Visual C\+\+)\b/i.test(serverPlatform)) put("platform", "WINDOWS", ["os.kernel_version"], "Database server platform.");
    else missing.push("Database server platform");

    const volumeRows = table("overview.database_volume");
    const volumes = new Map(volumeRows.filter(r => positive(r.database_size_bytes))
      .map(r => [r.database_name, Number(r.database_size_bytes)]));
    if (volumes.size) put("db_size", bytes([...volumes.values()].reduce((a, b) => a + b, 0)),
      ["overview.database_volume"], `Sum of ${volumes.size} distinct collected databases; omitted databases are not estimated.`);
    const connections = positive(setting("max_connections"));
    if (connections && Number.isInteger(connections)) {
      for (const field of ["min_conns", "max_conns"]) put(field, connections, ["overview.pg_settings"],
        "Preserve the configured connection capacity when budgeting memory; an observed session count is not a capacity requirement.");
    }
    const workers = positive(setting("autovacuum_max_workers"));
    if (workers && Number.isInteger(workers)) {
      for (const field of ["min_autovac_workers", "max_autovac_workers"])
        put(field, workers, ["overview.pg_settings"], "Preserve the configured autovacuum worker capacity.");
    }
    const walLevel = setting("wal_level");
    if (["minimal", "replica", "hot_standby", "archive", "logical"].includes(walLevel)) {
      put("replication_mode", walLevel === "logical" ? "logical" : walLevel === "minimal" ? "none" : "physical",
        ["overview.pg_settings"], "Retain the server's WAL/replication capability, including temporarily disconnected replicas.");
    }
    const archive = setting("archive_mode");
    if (["on", "always", "off"].includes(archive)) put("pitr_enabled", archive !== "off",
      ["overview.pg_settings"], "Collected archive_mode; this does not prove backup recoverability.");
    if (setting("synchronous_standby_names") !== undefined)
      put("synchronous_standby_names", setting("synchronous_standby_names"), ["overview.pg_settings"], "Keep the current synchronous standby requirement.");
    const slots = table("replication.replication_slots");
    const physicalSlots = new Set(slots.filter(r => r.slot_type === "physical").map(r => r.slot_name)).size;
    // A slot and its sender are the same replica, so do not sum these counts.
    const senders = new Set(table("replication.physical_replication").filter(r => r.pid != null &&
      !slots.some(s => s.slot_type === "logical" && String(s.active_pid) === String(r.pid))).map(r => r.pid)).size;
    if (physicalSlots || senders) put("replica_count", Math.max(physicalSlots, senders),
      ["replication.replication_slots", "replication.physical_replication"], "Observed physical slots/senders, deduplicated; expected future replica count remains an operator decision.", "inferred");
    else if (inputs.replication_mode === "none") put("replica_count", 0, ["overview.pg_settings"], "Replication capability is disabled.");
    const subscriptions = new Map(volumeRows.filter(r => r.subscriptions != null).map(r => [r.database_name, Number(r.subscriptions)]));
    const subscriptionWorkers = new Set(table("replication.subscription_workers").map(r => r.subid ?? r.subname).filter(v => v != null)).size;
    const subscriptionCount = Math.max(subscriptionWorkers, [...subscriptions.values()].reduce((a,b) => a+b, 0));
    if (subscriptionCount > 0 && Number.isInteger(subscriptionCount)) {
      if (inputs.replication_mode !== "logical") put("replication_mode", "logical", ["replication.subscription_workers", "overview.database_volume"], "Logical subscriptions require the logical calculation profile.", "inferred");
      put("logical_subscription_count", subscriptionCount, ["replication.subscription_workers", "overview.database_volume"], "Distinct subscriptions on this node, not their parallel/synchronization workers.");
    }
    const segment = settingBytes("wal_segment_size");
    if (segment) put("wal_segment_size", bytes(segment), ["overview.pg_settings"], "Actual WAL segment size of this cluster.");
    const walItem = items["snapshot_charts_db.wal_growth_rate"], walResult = walItem?.result;
    if (walItem?.collection_status === "ok" && walResult?.kind === "chart") {
      const rates = (walResult.series || []).flatMap(s => /^(bytes\/s|B\/s)$/.test(s.unit || walResult.chart?.unit || "")
        ? (s.points || []).map(p => positive(p.value)).filter(v => v !== null) : []);
      if (rates.length) put("peak_wal_rate", bytes(Math.ceil(rates.reduce((a, b) => Math.max(a, b), 0))), ["snapshot_charts_db.wal_growth_rate"],
        "Largest measured interval WAL rate; future bursts can exceed this collection window.");
    }
    const walDirectory = directory + (Number(major) < 10 ? "/pg_xlog" : "/pg_wal");
    const walLink = table("os.symlinks_in_sensitive_paths").find(r => r.path === walDirectory && typeof r.target === "string");
    let walPath = walDirectory;
    if (walLink) {
      const parts = (walLink.target.startsWith("/") ? walLink.target : directory + "/" + walLink.target).split("/");
      const resolved = [];
      for (const part of parts) { if (part === "..") resolved.pop(); else if (part && part !== ".") resolved.push(part); }
      walPath = "/" + resolved.join("/");
    }
    const walMount = mountFor(walPath);
    if (walMount && walMount.available_bytes != null && Number.isFinite(Number(walMount.available_bytes))) {
      const budget = Math.floor(Math.min(32 * GiB, Number(walMount.available_bytes) * 0.25));
      if (budget >= GiB) put("wal_disk_budget", bytes(budget),
        walLink ? ["os.disk_usage", "os.symlinks_in_sensitive_paths"] : ["os.disk_usage"],
        `Initial WAL allowance: 25% of free space on ${walMount.mount_point}, capped at 32 GiB. Collected WAL symlinks are resolved. Confirm other space consumers and retention requirements.`, "inferred");
      else missing.push("At least 1 GiB of WAL allowance after reserving other filesystem space");
    }
    const available = table("cluster_inventory.extensions").map(r => r.name).filter(v => typeof v === "string");
    // LOAD-only modules (notably auto_explain) have no pg_available_extensions row.
    // A successfully preloaded module is evidence of availability, too.
    for (const name of ["shared_preload_libraries", "session_preload_libraries", "local_preload_libraries"]) {
      const libraries = String(setting(name) || "").split(",").map(v => v.trim().replace(/^"|"$/g, ""));
      available.push(...libraries.filter(v => /^[a-zA-Z_][\w-]*$/.test(v)));
    }
    if (table("cluster_inventory.extensions").length && available.includes("auto_explain")) put("available_extensions", [...new Set(available)].join(","),
      ["cluster_inventory.extensions", "overview.pg_settings"], "Available extensions plus successfully preloaded modules (including LOAD-only modules such as auto_explain).");
    else if (table("cluster_inventory.extensions").length)
      notes.push("Extension inventory does not establish availability of LOAD-only modules such as auto_explain; the configurator retains its explicit availability assumption.");
    notes.push("Workload duty defaults to mixed. Memory shares, query-memory amplification, outage tolerance and unmeasured storage score remain editable configurator assumptions; utilization alone cannot determine them.");
    if (settingsRows.some(r => r.pending_restart === true)) notes.push("Some settings await restart. Diff uses running pg_settings values, not pending configuration-file values.");
    return {ready: missing.length === 0, inputs, sources, notes, missing, currentConfig,
      settingCount: currentRows.length, server: runtime.database_hostname || runtime.database_name || "PostgreSQL"};
  }
  return {prepare};
});
