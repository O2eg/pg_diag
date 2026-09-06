"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const {spawnSync} = require("node:child_process");
const {prepare} = require("../../tools/report_debug/prepare_audit.cjs");
const Graph = require("../../src/pg_diag/render/graph/pg-diag-graph.js");
const definition = require("../../src/pg_diag/render/graph/graph.json");
const tool = path.resolve(__dirname, "../../tools/report_debug/prepare_audit.cjs");
const fixture = name => ({...require("../data/diagnostic_graph/" + name + ".json"), artifact_schema_version: 5});

test("audit context uses the exact graph, separating own findings, inherited colors and security scope", () => {
  const artifact = fixture("lab_snapshots"), original = JSON.stringify(artifact);
  const performance = prepare(artifact), security = prepare(artifact, "security");
  assert.deepEqual(performance.evaluation, Graph.evaluate(artifact, definition));
  assert.deepEqual(security.evaluation, performance.evaluation);
  const ids = [...performance.focus.scopeNodes, ...security.focus.scopeNodes];
  assert.equal(new Set(ids).size, ids.length);
  assert.deepEqual([...ids].sort(), [...performance.evaluation.order].sort());
  assert.ok(security.focus.scopeNodes.includes("network.access.auth"));
  assert.ok(!performance.focus.scopeNodes.includes("network.access.auth"));
  for (const context of [performance, security]) {
    assert.ok(context.focus.candidateNodes.length);
    for (const id of context.focus.candidateNodes) {
      assert.ok(["warn", "crit"].includes(context.evaluation.nodes[id].ownStatus));
      assert.ok(context.focus.scopeNodes.includes(id));
    }
    for (const id of context.focus.inheritedNodes) {
      assert.ok(!context.focus.candidateNodes.includes(id));
      assert.ok(["warn", "crit"].includes(context.evaluation.nodes[id].status));
    }
  }
  assert.equal(JSON.stringify(artifact), original);
  assert.equal(performance.engine.version, Graph.VERSION);
  assert.equal(Object.keys(performance.engine.files).length, 5);
  assert.ok(Object.values(performance.engine.files).every(value => /^[a-f0-9]{64}$/.test(value)));
});

test("incomplete captures keep unassessed directions and item pointers; engine reads include shared inputs", () => {
  const artifact = fixture("lab_one_shot_remote_db_only");
  artifact.items["custom/a~b"] = {collection_status: "error", title: "custom", severity_level: "high"};
  const context = prepare(artifact);
  assert.ok(context.focus.unassessedNodes.includes("cpu.utilization"));
  assert.equal(context.evaluation.nodes["cpu.utilization"].ownStatus, "no_data");
  assert.ok(context.focus.inheritedNodes.includes("cpu"));
  assert.ok(context.focus.evidenceItems.includes("custom/a~b"));
  assert.ok(context.evaluation.coverage.unboundItems.includes("custom/a~b"));
  assert.equal(context.itemIndex["custom/a~b"].pointer, "/items/custom~1a~0b");
  assert.equal(context.itemIndex["custom/a~b"].presence, "error");
  const full = prepare(fixture("lab_snapshots"));
  assert.ok(full.reads["cpu.iowait.write.wal"].includes("snapshot_charts_os.os_cpu_utilization"));
  assert.ok(full.focus.contextLinks.some(link => link.from === "disk.space" && link.to === "health.replication"));
  assert.ok(full.focus.contextLinks.some(link => link.from === "network.clients.churn" &&
    link.to === "cpu.session_churn" && link.kind === "related"));
});

test("preparation rejects incompatible schemas and scopes instead of fabricating a graph", () => {
  assert.throws(() => prepare(null), /schema-v5/);
  for (const artifact_schema_version of [undefined, 4, 6]) {
    assert.throws(() => prepare({artifact_schema_version, items: {}, runtime: {}}), /schema-v5/);
  }
  assert.throws(() => prepare(fixture("lab_snapshots"), "all"), /Scope/);
});

test("CLI extracts only HTML data, records provenance and refuses output replacement from any cwd", t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pg-diag-audit-context-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const source = path.join(dir, "report.json"), html = path.join(dir, "report.html");
  const text = JSON.stringify(fixture("lab_snapshots"));
  fs.writeFileSync(source, text);
  fs.writeFileSync(html, '<script>throw Error("Do not execute this script")</script>' +
    '<script type="application/json" id="pg-diag-artifact">' + text + '</script>');
  const run = (...args) => spawnSync(process.execPath, [tool, ...args], {cwd: dir, encoding: "utf8", timeout: 15000});
  const jsonOutput = path.join(dir, "out", "json-context.json"), htmlOutput = path.join(dir, "html-context.json");
  for (const [input, output] of [[source, jsonOutput], [html, htmlOutput]]) {
    const result = run(output, input);
    assert.equal(result.status, 0, result.stderr);
    const context = JSON.parse(fs.readFileSync(output, "utf8"));
    assert.equal(context.source.path, input);
    assert.equal(context.source.sha256, crypto.createHash("sha256").update(fs.readFileSync(input)).digest("hex"));
    assert.equal(fs.statSync(output).mode & 0o777, 0o600);
  }
  assert.deepEqual(JSON.parse(fs.readFileSync(jsonOutput)).evaluation, JSON.parse(fs.readFileSync(htmlOutput)).evaluation);
  const original = fs.readFileSync(jsonOutput);
  assert.notEqual(run(jsonOutput, source).status, 0);
  assert.deepEqual(fs.readFileSync(jsonOutput), original);
  assert.notEqual(run(source, source).status, 0);
  assert.notEqual(run(html, source).status, 0);
  const alias = path.join(dir, "alias.json");
  fs.symlinkSync(source, alias);
  assert.notEqual(run(alias, source).status, 0);
  assert.equal(fs.readFileSync(source, "utf8"), text);
  fs.writeFileSync(html, '<script data-id="pg-diag-artifact">' + text + '</script>');
  assert.match(run(path.join(dir, "bad-attribute.json"), html).stderr, /exactly one/);
  fs.writeFileSync(html, '<script id="pg-diag-artifact">{}</script><script id="pg-diag-artifact">{}</script>');
  const rejected = run(path.join(dir, "bad.json"), html);
  assert.notEqual(rejected.status, 0);
  assert.match(rejected.stderr, /exactly one/);
  assert.ok(!fs.existsSync(path.join(dir, "bad.json")));
});
