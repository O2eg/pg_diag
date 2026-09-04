"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const G = require("../../src/pg_diag/render/graph/pg-diag-graph.js");
const R = require("../../src/pg_diag/render/graph/pg-diag-graph-render.js");
const definition = require("../../src/pg_diag/render/graph/graph.json");
const fixture = require("../data/diagnostic_graph/lab_snapshots.json");

test("top-down layout centres parents over siblings and keeps labels apart", () => {
  const ev = G.evaluate(fixture, definition);
  for (const expanded of [R.initialExpanded(ev), new Set(ev.order), new Set()]) {
    const {positions, width, height} = R.layout(ev, expanded);
    const levels = new Map();
    for (const [id, p] of Object.entries(positions)) {
      const box = R.nodeBounds(p);
      assert.ok(box.left >= 0 && box.right <= width, id + " horizontal bounds");
      assert.ok(box.top >= 0 && box.bottom <= height, id + " vertical bounds");
      const row = levels.get(p.depth) || [];
      row.push({id, ...box}); levels.set(p.depth, row);
      const children = ev.nodes[id].children.filter(child => positions[child]);
      if (!children.length) continue;
      const points = children.map(child => positions[child]);
      assert.equal(p.x, (points[0].x + points[points.length - 1].x) / 2);
      assert.equal(new Set(points.map(child => child.y)).size, 1, "siblings share a row");
      assert.ok(points.every(child => child.y > p.y));
    }
    for (const row of levels.values()) {
      row.sort((a, b) => a.left - b.left);
      for (let i = 1; i < row.length; i++) assert.ok(row[i].left > row[i - 1].right, row[i].id + " label overlap");
    }
  }
});

test("cause routes are orthogonal and avoid unrelated circles and labels", () => {
  const ev = G.evaluate(fixture, definition);
  const {positions} = R.layout(ev, new Set(ev.order));
  for (const link of ev.links) {
    for (const lane of [0, 3]) {
      const route = R.causeRoute(positions[link.from], positions[link.to], positions, lane);
      assert.ok(!/NaN|undefined/.test(R.roundedPath(route)));
      for (let i = 1; i < route.length; i++) {
        const a = route[i - 1], b = route[i];
        assert.ok(a.x === b.x || a.y === b.y);
        for (const [id, p] of Object.entries(positions)) {
          if ([link.from, link.to].includes(id)) continue;
          const box = R.nodeBounds(p);
          const crosses = a.x === b.x ? a.x > box.left && a.x < box.right && Math.max(a.y, b.y) > box.top && Math.min(a.y, b.y) < box.bottom : a.y > box.top && a.y < box.bottom && Math.max(a.x, b.x) > box.left && Math.min(a.x, b.x) < box.right;
          assert.ok(!crosses, link.from + " -> " + link.to + " crosses " + id);
        }
      }
    }
  }
});

test("warning branches open to reveal contributors and root labels wrap without truncation", () => {
  const ev = G.evaluate(fixture, definition);
  const expanded = R.initialExpanded(ev);
  for (const id of ev.order) {
    if (["warn", "crit"].includes(ev.nodes[id].status) && ev.nodes[id].children.length) assert.ok(expanded.has(id));
  }
  assert.deepEqual(R.labelLines("Database security", 12), ["Database", "security"]);
  assert.ok(R.LAYOUT.rootRadius > R.LAYOUT.radius * 3);
});

test("inline details reserve real width and height without overlapping any node", () => {
  const ev = G.evaluate(fixture, definition);
  const expanded = new Set(ev.order);
  for (const id of ev.order) {
    for (const height of [460, 2400]) {
      const placed = R.layout(ev, expanded, {id, width: R.DETAIL_WIDTH, height});
      const p = placed.positions[id];
      assert.equal(p.cardHeight, height);
      assert.equal(p.cardWidth, R.DETAIL_WIDTH);
      const card = {left: p.x - p.cardWidth / 2, right: p.x + p.cardWidth / 2, top: p.y + p.cardOffset, bottom: p.y + p.cardOffset + height};
      assert.ok(card.left >= 0 && card.right <= placed.width);
      assert.ok(card.bottom <= placed.height);
      for (const [otherId, other] of Object.entries(placed.positions)) {
        if (otherId === id) continue;
        const b = R.nodeBounds(other);
        assert.ok(card.right <= b.left || card.left >= b.right || card.bottom <= b.top || card.top >= b.bottom, id + " details overlap " + otherId);
      }
      for (const childId of ev.nodes[id].children) {
        assert.ok(R.nodeBounds(placed.positions[childId]).top > card.bottom, "children must move below the entire card");
      }
    }
  }
});

test("cause routes avoid open detail cards as well as nodes", () => {
  const ev = G.evaluate(fixture, definition);
  const expanded = new Set(ev.order);
  for (const id of ev.order) {
    const {positions} = R.layout(ev, expanded, {id, width: R.DETAIL_WIDTH, height: 1200});
    for (const link of ev.links.filter(link => [link.from, link.to].includes(id))) {
      const route = R.causeRoute(positions[link.from], positions[link.to], positions, 0);
      assert.ok(!/NaN|undefined/.test(R.roundedPath(route)));
      for (let i = 1; i < route.length; i++) {
        const a = route[i - 1], b = route[i];
        for (const [otherId, other] of Object.entries(positions)) {
          if ([link.from, link.to].includes(otherId)) continue;
          const z = R.nodeBounds(other);
          const crosses = a.x === b.x ? a.x > z.left && a.x < z.right && Math.max(a.y, b.y) > z.top && Math.min(a.y, b.y) < z.bottom : a.y > z.top && a.y < z.bottom && Math.max(a.x, b.x) > z.left && Math.min(a.x, b.x) < z.right;
          assert.ok(!crosses, id + " cause route crosses " + otherId);
        }
      }
    }
  }
});

test("animation frames use cached geometry instead of forcing size measurements", () => {
  const source = require("node:fs").readFileSync(require.resolve("../../src/pg_diag/render/graph/pg-diag-graph-render.js"), "utf8");
  const paint = source.split("const paint = (progress) => {")[1].split("const finish = () => {")[0];
  assert.ok(paint.includes("framePositions"));
  assert.doesNotMatch(paint, /offsetHeight|offsetWidth|getBoundingClientRect/);
});
