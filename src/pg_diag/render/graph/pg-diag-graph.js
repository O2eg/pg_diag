/* pg_diag diagnostic graph traversal and public API. No external dependencies. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(require("./pg-diag-graph-data.js"), require("./pg-diag-graph-rules.js"));
  } else {
    root.PgDiagGraph = factory(root.PgDiagGraphData, root.PgDiagGraphRules);
  }
})(typeof self !== "undefined" ? self : this, function (Data, Rules) {
  "use strict";

  const VERSION = "1.0.0";
  const {
    STATUS, isFiniteNumber, clamp01, scale, maxScore, statusOf,
    fmtPct, fmtNum, fmtBytes, fmtSeconds, truncate, seriesStats,
    sumSeries, decodeCell, resultOf, tableRows, chartSeries, textOf,
    itemPresence, classifyProcess, makeFacts, createAccess, logWindowMinutes
  } = Data;
  const {THRESHOLDS, evaluators, pressureOf} = Rules;

  function dampByPressure(ctx, score, kind) {
    if (!isFiniteNumber(score)) return null;
    const pressure = pressureOf(ctx, kind);
    const factor = pressure === null ? 0.5 : 0.2 + 0.8 * pressure;
    if (pressure !== null && score >= 0.34) {
      ctx.fact("Resource pressure", {ok: "Low", warn: "Elevated", crit: "High"}[statusOf(pressure)]);
    }
    return score * factor;
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

  function requirementUnmet(requirement, runtime, node, presenceOf, logCollected) {
    if (requirement === "snapshots") return runtime.mode !== "snapshots";
    if (requirement === "host") return runtime.collection_mode === "remote-db-only";
    if (requirement === "log") {
      // When the log was collected, an absent log item is a catalog difference
      // (older artifact), not a missing --log-depth-time-min.
      if (logCollected) return false;
      const logItems = node.bindings.filter((binding) => binding.id.startsWith("server_log."));
      return logItems.length > 0 && logItems.every((binding) => ["absent", "skipped", "unsupported"].includes(presenceOf(binding.id)));
    }
    return null; // extension requirements are judged from item presence below
  }

  function buildHints(node, runtime, presenceOf, itemOf, logCollected) {
    const hints = [];
    const seen = new Set();
    const push = (text) => {
      if (text && !seen.has(text)) {
        seen.add(text);
        hints.push(text);
      }
    };
    for (const requirement of node.requires || []) {
      const unmet = requirementUnmet(requirement, runtime, node, presenceOf, logCollected);
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
    if (categories.log && !categories.log.collected && categories.log.missing && !logCollected) push(HINTS.log);
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
    const logCollected = Object.keys(items).some((itemId) => itemId.startsWith("server_log.") && ["present", "empty"].includes(presenceOf(itemId)));
    const evidencePool = (node) => {
      const scored = node.bindings.filter((binding) => binding.role !== "fact");
      return scored.length ? scored : node.bindings;
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
        ...createAccess(items, opts.onRead ? (itemId, method) => opts.onRead(nodeId, itemId, method) : null),
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
        logWindowMinutes: () => logWindowMinutes(runtime)
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
            // A declarative cap bounds nodes whose findings are real but are not a
            // failure of this root (configuration advice, duplicated security checks).
            if (isFiniteNumber(node.cap) && isFiniteNumber(value)) value = Math.min(value, node.cap);
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
        hints: buildHints(node, runtime, presenceOf, itemOf, logCollected),
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
