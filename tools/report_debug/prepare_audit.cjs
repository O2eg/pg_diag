#!/usr/bin/env node
"use strict";

// Compute the report's graph with the shipped engine, without a browser or LLM.
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const graphDir = path.resolve(__dirname, "../../src/pg_diag/render/graph");
const Graph = require(path.join(graphDir, "pg-diag-graph.js"));
const definition = require(path.join(graphDir, "graph.json"));
const hash = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
const pointer = id => "/items/" + id.replace(/~/g, "~0").replace(/\//g, "~1");
const object = value => value && typeof value === "object" && !Array.isArray(value);

function prepare(artifact, scope = "performance") {
  if (!["performance", "security"].includes(scope)) throw Error("Scope must be performance or security");
  if (!object(artifact) || artifact.artifact_schema_version !== 5 || !object(artifact.items) || !object(artifact.runtime))
    throw Error("Expected a schema-v5 pg_diag artifact with items and runtime objects");
  const reads = new Map();
  const evaluation = Graph.evaluate(artifact, definition, {onRead(node, item) {
    if (!reads.has(node)) reads.set(node, new Set());
    reads.get(node).add(item);
  }});
  const {nodes, order, links} = evaluation;
  const subtree = roots => {
    const ids = new Set();
    const walk = id => { ids.add(id); nodes[id].children.forEach(walk); };
    roots.forEach(walk);
    return ids;
  };
  // Network access is the same security posture under a resource root. Keep
  // it with security, without changing the engine's scores or global coverage.
  const securityRoots = ["database_security", "network.access"];
  const security = subtree(securityRoots);
  const roots = scope === "security" ? securityRoots : evaluation.roots.filter(id => id !== "database_security");
  const scoped = new Set(order.filter(id => scope === "security" ? security.has(id) : !security.has(id)));
  const problem = status => status === "warn" || status === "crit";
  const candidates = order.filter(id => scoped.has(id) && problem(nodes[id].ownStatus));
  const gaps = order.filter(id => scoped.has(id) && (nodes[id].status === "no_data" ||
    (nodes[id].ownStatus === "no_data" && nodes[id].evaluator !== "aggregate")));
  const inherited = order.filter(id => scoped.has(id) && problem(nodes[id].status) && !problem(nodes[id].ownStatus));
  const context = new Set(roots);
  for (const id of [...candidates, ...gaps]) {
    for (let current = id; current; current = nodes[current].parent) context.add(current);
  }
  // Generated directions have no cause links of their own. Include links of
  // their ancestors too, but never interpret this relationship as proof.
  const contextLinks = links.filter(link => context.has(link.from) || context.has(link.to));
  for (const link of contextLinks) { context.add(link.from); context.add(link.to); }
  const evidenceItems = new Set(evaluation.coverage.unboundItems);
  for (const id of context) {
    const node = nodes[id];
    for (const item of [...(node.evidence || []), ...(reads.get(id) || []),
      ...(node.inputBindings || node.bindings).map(binding => binding.id)]) evidenceItems.add(item);
  }
  const itemIndex = Object.fromEntries(Object.entries(artifact.items).map(([id, item]) => [id, {
    pointer: pointer(id), title: item.title || id, presence: Graph.itemPresence(item),
    collection_status: item.collection_status || null, severity_level: item.severity_level || null,
    database_scope: item.source_metadata?.database_scope || null,
    collected_at: item.collected_at || null, result_kind: item.result?.kind || null
  }]));
  const errors = order.filter(id => nodes[id].error).map(id => ({node: id, error: nodes[id].error}));
  return {
    schema_version: "pg_diag/audit-context-v1", scope,
    artifact: {artifact_schema_version: artifact.artifact_schema_version, generator: artifact.generator || null,
      report: artifact.report || null, runtime: artifact.runtime, diagnostics: artifact.diagnostics || []},
    engine: {version: Graph.VERSION, files: Object.fromEntries([
      "graph.json", "pg-diag-graph-data.js", "pg-diag-graph-rules.js", "pg-diag-graph-groups.js", "pg-diag-graph.js"
    ].map(file => [file, hash(fs.readFileSync(path.join(graphDir, file)))]))},
    evaluation,
    focus: {
      roots, scopeNodes: order.filter(id => scoped.has(id)), candidateNodes: candidates,
      inheritedNodes: inherited, unassessedNodes: gaps,
      contextNodes: order.filter(id => context.has(id)),
      contextLinks,
      crossScopeLinks: links.filter(link => scoped.has(link.from) !== scoped.has(link.to)),
      evidenceItems: [...evidenceItems].sort()
    },
    reads: Object.fromEntries([...reads].map(([id, items]) => [id, [...items].sort()])),
    itemIndex, errors,
    interpretation: {
      causeDirection: "from = symptom; to = possible cause; this is a hypothesis, not a proven causal edge",
      related: "shared evidence or related checks; no causal direction",
      parent: "diagnostic grouping and score propagation; not causality",
      priority: "own warn/crit statuses select candidates, not incident priorities or confirmed bottlenecks",
      enrichment: "Read original item results, metadata, query_texts, object_ddl and snapshots; this context does not contain their full raw data"
    }
  };
}

function readArtifact(input) {
  const bytes = fs.readFileSync(input);
  let text = bytes.toString("utf8");
  if (/\.html?$/i.test(input)) {
    const matches = [...text.matchAll(/<script\b(?=[^>]*\sid\s*=\s*["']pg-diag-artifact["'])[^>]*>([\s\S]*?)<\/script\s*>/gi)];
    if (matches.length !== 1) throw Error("Expected exactly one pg-diag-artifact JSON script");
    text = matches[0][1]; // Parse data only; never evaluate any code from HTML.
  }
  return {artifact: JSON.parse(text), sha256: hash(bytes)};
}

function main(args) {
  if (args.length === 1 && ["--help", "-h"].includes(args[0])) {
    console.log("Usage: node tools/report_debug/prepare_audit.cjs OUTPUT.json REPORT.json|REPORT.html [performance|security]");
    return;
  }
  if (args.length < 2 || args.length > 3) throw Error("Use --help for usage");
  const [outputArg, inputArg, scope = "performance"] = args;
  const input = path.resolve(inputArg), output = path.resolve(outputArg);
  const stem = input.replace(/\.(json|html?)$/i, "");
  if ([input, stem + ".json", stem + ".html", stem + ".htm"].includes(output))
    throw Error("Output must differ from the input and its companions");
  const {artifact, sha256} = readArtifact(input);
  const result = {source: {path: input, sha256}, ...prepare(artifact, scope)};
  fs.mkdirSync(path.dirname(output), {recursive: true});
  // A fresh output also prevents replacement through a symlink or hard link.
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n", {flag: "wx", mode: 0o600});
  console.log(JSON.stringify({output, scope, candidates: result.focus.candidateNodes.length,
    unassessed: result.focus.unassessedNodes.length, unbound: result.evaluation.coverage.unboundItems.length,
    errors: result.errors.length}));
  if (result.errors.length) process.exitCode = 1;
}

if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 2; }
}
module.exports = {prepare, readArtifact};
