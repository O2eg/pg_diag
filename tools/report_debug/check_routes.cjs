#!/usr/bin/env node
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../../src/pg_diag/render/graph");
const G = require(path.join(root, "pg-diag-graph.js"));
const R = require(path.join(root, "pg-diag-graph-render.js"));
const definition = require(path.join(root, "graph.json"));

function intersects(a, b, box) {
  return a.x === b.x
    ? a.x > box.left && a.x < box.right && Math.max(a.y, b.y) > box.top && Math.min(a.y, b.y) < box.bottom
    : a.y > box.top && a.y < box.bottom && Math.max(a.x, b.x) > box.left && Math.min(a.x, b.x) < box.right;
}

const boundsCache = new WeakMap();
function checkRoute(route, positions, link, treeEdge = false) {
  const problems = [];
  if (route.some(p => !Number.isFinite(p.x) || !Number.isFinite(p.y))) return ["non-finite route"];
  let boxes = boundsCache.get(positions);
  if (!boxes) {
    boxes = Object.entries(positions).flatMap(([id, p]) => {
      const result = [{id, card: false, ...R.nodeBounds({...p, cardHeight: 0})}];
      if (p.cardHeight) result.push({id, card: true,
        left: p.x - p.cardWidth / 2, right: p.x + p.cardWidth / 2,
        top: p.y + p.cardOffset, bottom: p.y + p.cardOffset + p.cardHeight});
      return result;
    });
    boundsCache.set(positions, boxes);
  }
  for (let index = 1; index < route.length; index++) {
    const a = route[index - 1], b = route[index];
    if (a.x !== b.x && a.y !== b.y) problems.push("non-orthogonal segment");
    for (const box of boxes) {
      // Endpoint ports touch the circle's bounding square by design.
      if (box.card ? treeEdge && box.id === link.from : [link.from, link.to].includes(box.id)) continue;
      if (intersects(a, b, box)) problems.push((box.card ? 'card:' : 'node:') + box.id);
    }
  }
  return [...new Set(problems)];
}

function auditTree(evaluation) {
  const failures = []; let routes = 0, cases = 0;
  const scenarios = [new Set(evaluation.roots), new Set(evaluation.order)];
  for (let seed = 1; seed <= 12; seed++) {
    let value = seed;
    scenarios.push(new Set(evaluation.order.filter(() => {
      value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
      return value / 4294967296 < 0.75;
    })));
  }
  for (const [scenario, expanded] of scenarios.entries()) {
    const baseline = R.layout(evaluation, expanded);
    const details = [null, ...Object.keys(baseline.positions).flatMap(id =>
      [460, 1200, 2400].map(height => ({id, height, width: R.DETAIL_WIDTH})))];
    for (const detail of details) {
      cases++;
      const {positions} = detail ? R.layout(evaluation, expanded, detail) : baseline;
      const obstacles = R.routingObstacles(positions);
      for (const [id, to] of Object.entries(positions)) {
        const parent = evaluation.nodes[id].parent, from = positions[parent];
        if (!from) continue;
        const link = {from: parent, to: id}, route = R.treeRoute(from, to);
        const problems = checkRoute(route, positions, link, true);
        if (!R.causeRouteClear(route, from, to, positions, true, obstacles)) problems.push('hidden-settled-edge');
        routes++;
        if (problems.length) failures.push({scenario, detail, link, problems, route});
      }
    }
  }
  return {cases, routes, failures, passed: !failures.length};
}

function visibleCombinations(evaluation, causeOnly = false) {
  const links = evaluation.links.filter(link => !causeOnly || link.kind !== 'related');
  const ancestors = id => {
    const result = [];
    while (evaluation.nodes[id].parent) {id = evaluation.nodes[id].parent; result.push(id);}
    return result;
  };
  const sets = new Set(['']), cases = [];
  let maxVisible = 0;
  for (const id of evaluation.order) {
    const incident = links.map((link, index) => ({link, index})).filter(({link}) => [link.from, link.to].includes(id));
    if (!incident.length) continue;
    for (let mask = 0; mask < 2 ** incident.length; mask++) {
      const expanded = new Set(ancestors(id)), included = [];
      incident.forEach(({link, index}, bit) => {
        if (!(mask & (1 << bit))) return;
        included.push(index);
        for (const parent of ancestors(link.from === id ? link.to : link.from)) expanded.add(parent);
      });
      // If an excluded endpoint's ancestors are already required, it cannot
      // be hidden independently (e.g. two siblings revealed by one parent).
      if (!incident.every(({link}, bit) => (mask & (1 << bit)) || ancestors(link.from === id ? link.to : link.from).some(parent => !expanded.has(parent)))) continue;
      sets.add(included.join(','));
      maxVisible = Math.max(maxVisible, included.length);
      cases.push({selected: id, links: included.map(index => links[index]), expanded: [...expanded]});
    }
  }
  return {distinctSetsIncludingEmpty: sets.size, maxVisible, cases};
}

function audit(evaluation) {
  const failures = []; let routes = 0;
  for (const link of evaluation.links) {
    const branch = new Set();
    for (let id of [link.from, link.to]) {
      while (id) {branch.add(id); id = evaluation.nodes[id].parent;}
    }
    const scenarios = [
      ["branches", branch], ["root-children", new Set([...evaluation.roots, ...branch])],
      ["all", new Set(evaluation.order)]
    ];
    for (let seed = 1; seed <= 12; seed++) {
      let value = seed;
      scenarios.push(["mixed-" + seed, new Set([...branch, ...evaluation.order.filter(() => {
        value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
        return value / 4294967296 < 0.65;
      })])]);
    }
    for (const [name, expanded] of scenarios) for (const selected of [link.from, link.to]) for (const height of [0, 460, 1200, 2400]) {
      const {positions} = R.layout(evaluation, expanded, height ? {id: selected, width: R.DETAIL_WIDTH, height} : null);
      for (const lane of [0, 3]) {
        const route = R.causeRoute(positions[link.from], positions[link.to], positions, lane);
        const problems = checkRoute(route, positions, link);
        if (R.causeRouteClear && !R.causeRouteClear(route, positions[link.from], positions[link.to], positions)) problems.push('hidden-settled-link');
        routes++;
        if (problems.length) failures.push({link, scenario: name, selected, height, lane, problems, route});
      }
    }
  }
  const tree = auditTree(evaluation);
  return {links: evaluation.links.length, routes, failures, tree, passed: !failures.length && tree.passed,
    combinations: {causes: visibleCombinations(evaluation, true), all: visibleCombinations(evaluation)}};
}

if (require.main === module) {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    console.error("Usage: node tools/report_debug/check_routes.cjs ARTIFACT.json OUTPUT.json");
    process.exit(2);
  }
  if (path.resolve(input) === path.resolve(output)) throw Error('Output must differ from input');
  const artifact = JSON.parse(fs.readFileSync(input, "utf8"));
  const result = audit(G.evaluate(artifact, definition));
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n", {mode: 0o600});
  console.log(JSON.stringify({links: result.links, routes: result.routes, failures: result.failures.length,
    treeCases: result.tree.cases, treeRoutes: result.tree.routes, treeFailures: result.tree.failures.length}));
  process.exitCode = result.passed ? 0 : 1;
}
module.exports = {audit, auditTree, checkRoute, intersects, visibleCombinations};
