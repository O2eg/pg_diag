#!/usr/bin/env node
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../../src/pg_diag/render/graph");
const G = require(path.join(root, "pg-diag-graph.js"));
const definition = require(path.join(root, "graph.json"));
const [output, ...inputs] = process.argv.slice(2);
if (!output || !inputs.length) {
  console.error("Usage: node tools/report_debug/evaluate.cjs OUTPUT.json REPORT.json [...]");
  process.exit(2);
}
if (inputs.some(input => path.resolve(input) === path.resolve(output))) throw Error("Output must differ from inputs");
const results = [];
for (const input of inputs) {
  const artifact = JSON.parse(fs.readFileSync(input, "utf8"));
  if (!artifact.items || !artifact.runtime) throw Error("Not a pg_diag artifact: " + input);
  const evaluation = G.evaluate(artifact, definition);
  const nodes = Object.values(evaluation.nodes), seen = new Map(), contradictions = [];
  for (const node of nodes.filter(n => n.kind === "sources")) {
    const key = node.evaluator + ":" + node.bindings.map(b => b.id).sort().join(",");
    const old = seen.get(key);
    if (old && old.ownScore !== node.ownScore) contradictions.push([old.id, node.id]);
    seen.set(key, node);
  }
  const errors = nodes.filter(n => n.error).map(n => [n.id, n.error]);
  results.push({path: path.resolve(input), runtime: artifact.runtime, coverage: evaluation.coverage,
    contradictions, errors, roots: evaluation.roots, nodes: evaluation.nodes});
  console.log(JSON.stringify({report: input, statuses: evaluation.coverage.statusCounts,
    unbound: evaluation.coverage.unboundItems, errors, contradictions}));
}
fs.writeFileSync(output, JSON.stringify(results, null, 2) + "\n", {mode: 0o600});
process.exitCode = results.some(r => r.errors.length || r.contradictions.length || r.coverage.unboundItems.length) ? 1 : 0;
