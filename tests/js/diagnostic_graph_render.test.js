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
    const radii = new Map();
    for (const [id, p] of Object.entries(positions)) {
      if (radii.has(p.depth)) assert.equal(p.radius, radii.get(p.depth), "equal circles at each depth");
      radii.set(p.depth, p.radius);
      if (ev.nodes[id].parent) assert.ok(positions[ev.nodes[id].parent].radius > p.radius, "parents are larger than children");
      const box = R.nodeBounds(p);
      assert.ok(box.left >= 0 && box.right <= width, id + " horizontal bounds");
      assert.ok(box.top >= 0 && box.bottom <= height, id + " vertical bounds");
      const row = levels.get(p.y) || [];
      row.push({id, ...box}); levels.set(p.y, row);
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
    const lowerRoots = ["database_health", "database_security"];
    const upperPositions = Object.entries(positions).filter(([id]) => {
      while (ev.nodes[id].parent) id = ev.nodes[id].parent;
      return !lowerRoots.includes(id);
    }).map(([, p]) => p);
    const upperBottom = Math.max(...upperPositions.map(p => R.nodeBounds(p).bottom));
    assert.equal(positions.database_health.y, positions.database_security.y);
    for (const id of lowerRoots) assert.ok(R.nodeBounds(positions[id]).top > upperBottom);
  }
});

test("lower roots follow resource expansion and details without moving the upper row", () => {
  const ev = G.evaluate(fixture, definition);
  const closed = R.layout(ev, new Set());
  const expanded = new Set(["cpu"]);
  const open = R.layout(ev, expanded);
  const withCard = R.layout(ev, expanded, {id: "cpu", width: R.DETAIL_WIDTH, height: 1200});
  for (const id of ["database_health", "database_security"]) {
    assert.ok(open.positions[id].y > closed.positions[id].y);
    assert.ok(withCard.positions[id].y > open.positions[id].y);
  }
  const lowerCard = R.layout(ev, expanded, {id: "database_health", width: R.DETAIL_WIDTH, height: 2400});
  for (const id of Object.keys(open.positions)) {
    if (id === "database_health" || id === "database_security") continue;
    assert.deepEqual(lowerCard.positions[id], open.positions[id]);
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

test("initial view shows only six roots even when descendants have findings", () => {
  const ev = G.evaluate(fixture, definition);
  const expanded = R.initialExpanded(ev);
  assert.equal(expanded.size, 0);
  assert.deepEqual(Object.keys(R.layout(ev, expanded).positions), ev.roots);
  assert.deepEqual(R.labelLines("Database security", 12), ["Database", "security"]);
  assert.ok(R.LAYOUT.rootRadius > R.LAYOUT.radius);
});

test("circle captions preserve 50 characters, truncate longer text and wrap long words", () => {
  for (const character of ["W", "Ж", "😀"]) {
    const exact = character.repeat(50);
    assert.equal(R.truncateLabel(exact, 50), exact);
    const clipped = R.truncateLabel(exact + character, 50);
    assert.equal(clipped, character.repeat(49) + "…");
    for (const text of [exact, clipped]) {
      const lines = R.labelLines(text, R.LAYOUT.labelWrapChars);
      assert.equal(lines.join(""), text);
      assert.ok(lines.every(line => Array.from(line).length <= R.LAYOUT.labelWrapChars));
    }
  }
});

test("inline details reserve real width and height without overlapping any node", () => {
  const ev = G.evaluate(fixture, definition);
  const expanded = new Set(ev.order);
  const baseline = R.layout(ev, expanded).positions;
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
        let root = otherId, descendant = false;
        while (ev.nodes[root].parent) {
          root = ev.nodes[root].parent;
          if (root === id) descendant = true;
        }
        if (!descendant) {
          assert.equal(other.y - placed.positions[root].y, baseline[otherId].y - baseline[root].y,
            id + " details must not stretch unrelated branch " + otherId);
        }
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
