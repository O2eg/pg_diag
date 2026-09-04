/*
 * pg_diag diagnostic graph renderer.
 *
 * Draws the evaluation produced by pg-diag-graph.js as top-down trees on a
 * pannable, zoomable SVG canvas, with inline expandable details below nodes.
 * Scores drive colors, not percentage labels. Everything else is themed
 * through the report CSS variables. No dependencies.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.PgDiagGraphRender = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const LAYOUT = {
    siblingGap: 24,
    treeGap: 64,
    levelHeight: 156,
    rootRadius: 76,
    radius: 18,
    marginX: 24,
    marginTop: 24,
    marginBottom: 72,
    labelMaxChars: 19,
    labelLineHeight: 18
  };
  const STORAGE_KEY = "pg-diag-graph-collapsed";
  const MIN_ZOOM = 0.05;
  const MAX_ZOOM = 4;
  const DETAIL_WIDTH = 520;
  const MOTION_MS = 300;
  const instances = new WeakMap();

  function el(tag, className, parent, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function svgEl(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value !== null && value !== undefined) node.setAttribute(key, String(value));
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  function scoreColor(score) {
    if (typeof score !== "number" || !Number.isFinite(score)) {
      return null;
    }
    // green (130) -> yellow (48) -> red (4)
    const hue = score < 0.5 ? 130 - (130 - 48) * (score / 0.5) : 48 - (48 - 4) * ((score - 0.5) / 0.5);
    return "hsl(" + hue.toFixed(0) + " var(--dg-node-sat, 62%) var(--dg-node-light, 46%))";
  }

  function statusLabel(status) {
    return {ok: "OK", warn: "Warning", crit: "Critical", no_data: "No data"}[status] || status;
  }

  function truncateLabel(text, maxChars) {
    const value = String(text || "");
    return value.length > maxChars ? value.slice(0, maxChars - 1) + "…" : value;
  }

  function labelLines(text, maxChars) {
    const words = String(text || "").trim().split(/\s+/);
    const lines = [];
    let line = "";
    for (const word of words) {
      if (line && (line + " " + word).length > maxChars) {
        lines.push(line);
        line = word;
      } else {
        line = line ? line + " " + word : word;
      }
    }
    if (line) lines.push(line);
    return lines;
  }

  function readCollapsed() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === "1";
    } catch (error) {
      return false;
    }
  }

  function writeCollapsed(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
    } catch (error) {
      /* storage may be unavailable */
    }
  }

  // ------------------------------------------------------------ layout

  // Visible set: roots, their children, and every ancestor chain of warn/crit
  // nodes; other subtrees stay collapsed until the user expands them.
  function initialExpanded(evaluation) {
    const expanded = new Set();
    for (const rootId of evaluation.roots) expanded.add(rootId);
    for (const nodeId of evaluation.order) {
      const node = evaluation.nodes[nodeId];
      if (node.status === "crit" || node.status === "warn") {
        if (node.children.length) expanded.add(nodeId);
        let cursor = node.parent;
        while (cursor) {
          expanded.add(cursor);
          cursor = evaluation.nodes[cursor].parent;
        }
      }
    }
    return expanded;
  }

  // Each subtree owns a horizontal span. Siblings share a depth row, and their
  // parent is centred over the first and last child (not a depth-first list).
  function layout(evaluation, expanded, detail) {
    const nodes = evaluation.nodes;
    const positions = {};
    const spans = {};
    const rowBottoms = [];
    const rowY = [LAYOUT.marginTop + LAYOUT.rootRadius];
    let maxBottom = 0;
    const childrenOf = (id) => expanded.has(id) ? nodes[id].children : [];
    const measure = (id, depth) => {
      const lines = labelLines(nodes[id].label, depth === 0 ? 12 : LAYOUT.labelMaxChars);
      const radius = depth === 0 ? LAYOUT.rootRadius : LAYOUT.radius;
      const labelWidth = depth === 0 ? radius * 2 : Math.max(72, ...lines.map((line) => line.length * 8));
      const labelBottom = radius + (depth === 0 ? 4 : 14 + lines.length * LAYOUT.labelLineHeight);
      const cardHeight = detail && detail.id === id ? detail.height : 0;
      const cardWidth = cardHeight ? detail.width : 0;
      const cardOffset = labelBottom + 18;
      const ownWidth = Math.max(labelWidth, cardWidth);
      rowBottoms[depth] = Math.max(rowBottoms[depth] || 0, cardHeight ? cardOffset + cardHeight : labelBottom);
      const children = childrenOf(id);
      let cursor = 0;
      const offsets = [];
      for (const child of children) {
        measure(child, depth + 1);
        offsets.push(cursor);
        cursor += spans[child].width + LAYOUT.siblingGap;
      }
      const childrenWidth = Math.max(0, cursor - LAYOUT.siblingGap);
      const anchor = children.length ? (spans[children[0]].anchor + offsets[offsets.length - 1] + spans[children[children.length - 1]].anchor) / 2 : ownWidth / 2;
      // Reserve both sides of the parent/card even with asymmetric children.
      const left = Math.min(0, anchor - ownWidth / 2);
      const right = Math.max(childrenWidth, anchor + ownWidth / 2);
      spans[id] = {width: right - left, anchor: anchor - left, offsets: offsets.map(x => x - left), lines, radius, labelWidth, cardHeight, cardWidth, cardOffset};
      return spans[id].width;
    };
    const place = (id, depth, left) => {
      const span = spans[id];
      const children = childrenOf(id);
      children.forEach((child, index) => place(child, depth + 1, left + span.offsets[index]));
      const {radius, labelWidth, cardHeight, cardWidth, cardOffset, lines} = span;
      positions[id] = {x: left + span.anchor, y: rowY[depth], depth, radius, lines, labelWidth, cardHeight, cardWidth, cardOffset};
      maxBottom = Math.max(maxBottom, nodeBounds(positions[id]).bottom);
    };
    for (const id of evaluation.roots) measure(id, 0);
    for (let depth = 1; depth < rowBottoms.length; depth++) {
      rowY[depth] = rowY[depth - 1] + Math.max(LAYOUT.levelHeight, rowBottoms[depth - 1] + LAYOUT.radius + 56);
    }
    let left = LAYOUT.marginX;
    for (const id of evaluation.roots) {
      place(id, 0, left);
      left += spans[id].width + LAYOUT.treeGap;
    }
    return {positions, width: left - LAYOUT.treeGap + LAYOUT.marginX, height: maxBottom + LAYOUT.marginBottom};
  }

  // ------------------------------------------------------------ canvas

  function viewportSize(state) {
    return {width: state.svg.clientWidth, height: state.svg.clientHeight};
  }

  function applyView(state) {
    const {x, y, scale} = state.view;
    if (state.scene) state.scene.setAttribute("transform", "translate(" + x + "," + y + ") scale(" + scale + ")");
    state.zoomValue.textContent = scale.toFixed(2) + "×";
    state.zoomOut.disabled = scale <= MIN_ZOOM;
    state.zoomIn.disabled = scale >= MAX_ZOOM;
  }

  function fitView(state) {
    const {width, height} = viewportSize(state);
    if (!width || !height || !state.bounds) return;
    const scale = Math.max(MIN_ZOOM, Math.min(1, (width - 48) / state.bounds.width, (height - 96) / state.bounds.height));
    state.view = {scale, x: (width - state.bounds.width * scale) / 2, y: 48 + (height - 96 - state.bounds.height * scale) / 2};
    state.autoFit = true;
    applyView(state);
  }

  function zoomAt(state, target, point) {
    const scale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, target));
    const {width, height} = viewportSize(state);
    const anchor = point || {x: width / 2, y: height / 2};
    const ratio = scale / state.view.scale;
    state.view.x = anchor.x - (anchor.x - state.view.x) * ratio;
    state.view.y = anchor.y - (anchor.y - state.view.y) * ratio;
    state.view.scale = scale;
    state.autoFit = false;
    applyView(state);
  }

  function attachViewport(state) {
    const controls = el("div", "dg-zoom", state.canvas);
    controls.setAttribute("role", "group");
    controls.setAttribute("aria-label", "Graph zoom controls");
    const button = (label, name, handler) => {
      const control = el("button", "dg-zoom-button", controls, label);
      control.type = "button";
      control.title = name;
      control.setAttribute("aria-label", name);
      control.addEventListener("click", handler);
      return control;
    };
    state.zoomOut = button("−", "Zoom out", () => zoomAt(state, state.view.scale / 1.4));
    state.zoomValue = el("output", "dg-zoom-value", controls);
    state.zoomValue.setAttribute("aria-label", "Zoom level");
    state.zoomIn = button("+", "Zoom in", () => zoomAt(state, state.view.scale * 1.4));
    button("Fit", "Fit graph", () => fitView(state));
    button("1:1", "Actual size", () => zoomAt(state, 1));
    el("span", "dg-canvas-hint", state.canvas, "Drag to pan · Scroll to zoom");

    // Like pg_explain_viewer: don't capture a press until it becomes a drag,
    // then swallow its trailing click so dragging a node never selects it.
    let drag = null;
    let suppressClick = false;
    const svg = state.svg;
    svg.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || drag) return;
      if (event.target.closest("button, a, input, select, textarea")) return;
      suppressClick = false;
      drag = {id: event.pointerId, x: event.clientX, y: event.clientY, lastX: event.clientX, lastY: event.clientY, moved: false};
    });
    svg.addEventListener("pointermove", (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      // A mouse released outside the SVG before capture must not leave a drag.
      if (event.pointerType === "mouse" && !(event.buttons & 1)) { drag = null; return; }
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
      if (!drag.moved) {
        drag.moved = true;
        svg.setPointerCapture(event.pointerId);
        state.canvas.classList.add("dg-grabbing");
      }
      state.view.x += event.clientX - drag.lastX;
      state.view.y += event.clientY - drag.lastY;
      drag.lastX = event.clientX;
      drag.lastY = event.clientY;
      state.autoFit = false;
      applyView(state);
      event.preventDefault();
    });
    const end = (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      suppressClick = drag.moved;
      drag = null;
      state.canvas.classList.remove("dg-grabbing");
      if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    };
    svg.addEventListener("pointerup", end);
    svg.addEventListener("pointercancel", end);
    svg.addEventListener("lostpointercapture", end);
    svg.addEventListener("click", (event) => {
      if (suppressClick && event.detail !== 0) {
        suppressClick = false;
        event.stopPropagation();
        event.preventDefault();
      }
    }, true);
    svg.addEventListener("wheel", (event) => {
      event.preventDefault();
      const rect = svg.getBoundingClientRect();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
      zoomAt(state, state.view.scale * Math.exp(-Math.max(-500, Math.min(500, delta)) * 0.002), {x: event.clientX - rect.left, y: event.clientY - rect.top});
    }, {passive: false});
    svg.addEventListener("keydown", (event) => {
      if (event.target.closest(".dg-panel")) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === "+" || event.key === "=") zoomAt(state, state.view.scale * 1.4);
      else if (event.key === "-") zoomAt(state, state.view.scale / 1.4);
      else if (event.key === "0" || event.key === "Home") fitView(state);
      else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        state.view.x += event.key === "ArrowLeft" ? 50 : event.key === "ArrowRight" ? -50 : 0;
        state.view.y += event.key === "ArrowUp" ? 50 : event.key === "ArrowDown" ? -50 : 0;
        state.autoFit = false;
        applyView(state);
      } else return;
      event.preventDefault();
    });
    if (typeof ResizeObserver !== "undefined") {
      let previous = viewportSize(state);
      state.resizeObserver = new ResizeObserver(() => {
        const size = viewportSize(state);
        if (!size.width || !size.height) return;
        if (state.autoFit) fitView(state);
        else if (previous.width && previous.height) {
          state.view.x += (size.width - previous.width) / 2;
          state.view.y += (size.height - previous.height) / 2;
          applyView(state);
        }
        previous = size;
      });
      state.resizeObserver.observe(svg);
    }
  }
  // ------------------------------------------------------------ drawing

  function edgePath(from, to) {
    if (from.cardHeight) from = {...from, y: from.y + from.cardOffset + from.cardHeight, radius: 0};
    const distance = Math.hypot(to.x - from.x, to.y - from.y) || 1;
    const ux = (to.x - from.x) / distance;
    const uy = (to.y - from.y) / distance;
    return "M" + (from.x + ux * from.radius) + "," + (from.y + uy * from.radius) + " L" + (to.x - ux * to.radius) + "," + (to.y - uy * to.radius);
  }

  function nodeBounds(position) {
    const width = Math.max(position.labelWidth, position.cardHeight ? position.cardWidth : 0);
    return {left: position.x - width / 2 - 4, right: position.x + width / 2 + 4,
      top: position.y - position.radius - 4,
      bottom: position.y + (position.cardHeight ? position.cardOffset + position.cardHeight : position.radius + (position.depth === 0 ? 4 : 14 + position.lines.length * LAYOUT.labelLineHeight))};
  }

  // Route causes through level gutters and a free vertical lane. Only links
  // involving the selection are drawn, so unrelated branches stay legible.
  function causeRoute(from, to, positions, lane) {
    const offset = 28 + Math.min(lane || 0, 3) * 4;
    const side = to.x >= from.x ? 1 : -1;
    const exitX = from.x + side * (from.labelWidth / 2 + 16);
    const fromY = from.y - from.radius - offset;
    const toY = to.y - to.radius - offset;
    const boxes = Object.values(positions).map(nodeBounds);
    const candidates = [exitX, to.x];
    for (const box of boxes) candidates.push(box.left - 12, box.right + 12);
    const minY = Math.min(fromY, toY);
    const maxY = Math.max(fromY, toY);
    const lanes = candidates.filter((x) => !boxes.some((box) => x > box.left - 6 && x < box.right + 6 && minY < box.bottom + 6 && maxY > box.top - 6));
    const trunkX = lanes.sort((a, b) => (Math.abs(a - exitX) + Math.abs(a - to.x)) - (Math.abs(b - exitX) + Math.abs(b - to.x)))[0];
    const points = [
      {x: from.x + side * from.radius, y: from.y}, {x: exitX, y: from.y},
      {x: exitX, y: fromY}, {x: trunkX, y: fromY}, {x: trunkX, y: toY},
      {x: to.x, y: toY}, {x: to.x, y: to.y - to.radius - 6}
    ];
    const compact = [];
    for (const point of points) {
      const last = compact[compact.length - 1];
      if (last && last.x === point.x && last.y === point.y) continue;
      while (compact.length > 1) {
        const a = compact[compact.length - 2];
        const b = compact[compact.length - 1];
        if ((a.x === b.x && b.x === point.x) || (a.y === b.y && b.y === point.y)) compact.pop();
        else break;
      }
      compact.push(point);
    }
    return compact;
  }

  function roundedPath(points) {
    let path = "M" + points[0].x + "," + points[0].y;
    for (let index = 1; index < points.length - 1; index++) {
      const a = points[index - 1], b = points[index], c = points[index + 1];
      const incoming = Math.hypot(b.x - a.x, b.y - a.y);
      const outgoing = Math.hypot(c.x - b.x, c.y - b.y);
      const radius = Math.min(8, incoming / 2, outgoing / 2);
      const before = {x: b.x + (a.x - b.x) * radius / incoming, y: b.y + (a.y - b.y) * radius / incoming};
      const after = {x: b.x + (c.x - b.x) * radius / outgoing, y: b.y + (c.y - b.y) * radius / outgoing};
      path += " L" + before.x + "," + before.y + " Q" + b.x + "," + b.y + " " + after.x + "," + after.y;
    }
    const end = points[points.length - 1];
    return path + " L" + end.x + "," + end.y;
  }

  function ensureCard(state, nodeId) {
    if (!nodeId) return null;
    if (state.cards.has(nodeId)) return state.cards.get(nodeId);
    const panel = el("section", "dg-panel", state.measurer);
    panel.setAttribute("aria-label", state.evaluation.nodes[nodeId].label + " details");
    drawPanel(state, nodeId, panel);
    const card = {id: nodeId, width: DETAIL_WIDTH, height: Math.max(1, panel.offsetHeight), panel};
    card.element = svgEl("foreignObject", {class: "dg-detail", width: card.width, "data-node-id": nodeId});
    card.element.appendChild(panel);
    state.cards.set(nodeId, card);
    if (typeof ResizeObserver !== "undefined") {
      card.observer = new ResizeObserver(() => {
        const height = panel.offsetHeight;
        if (state.detailsId === nodeId && height > 0 && height !== card.height) {
          card.height = height;
          drawGraph(state);
        }
      });
      card.observer.observe(panel);
    }
    return card;
  }

  function nearestPosition(evaluation, nodeId, positions) {
    let cursor = evaluation.nodes[nodeId].parent;
    while (cursor) {
      if (positions[cursor]) return positions[cursor];
      cursor = evaluation.nodes[cursor].parent;
    }
    return null;
  }

  function drawGraph(state, animate) {
    const {evaluation, expanded, svg} = state;
    if (state.frame) cancelAnimationFrame(state.frame);
    state.frame = null;
    const before = state.displayPositions || {};
    const beforeOpacity = state.displayOpacity || {};
    const detail = ensureCard(state, state.detailsId);
    const target = layout(evaluation, expanded, detail);
    const positions = target.positions;
    state.positions = positions;
    state.bounds = {width: target.width, height: target.height};
    const ids = [...new Set([...Object.keys(before), ...Object.keys(positions)])];
    const starts = {}, ends = {};
    for (const id of ids) {
      const origin = nearestPosition(evaluation, id, before) || positions[id];
      const destination = nearestPosition(evaluation, id, positions) || before[id];
      starts[id] = before[id] || {...positions[id], x: origin.x, y: origin.y, cardHeight: 0};
      ends[id] = positions[id] || {...before[id], x: destination.x, y: destination.y, cardHeight: 0};
    }
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const defs = svgEl("defs", {}, svg);
    const marker = svgEl("marker", {id: "dg-arrow", viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse"}, defs);
    svgEl("path", {d: "M0,0 L10,5 L0,10 z", class: "dg-arrow"}, marker);

    state.scene = svgEl("g", {class: "dg-scene"}, svg);
    const edges = svgEl("g", {class: "dg-edges"}, state.scene);
    const links = svgEl("g", {class: "dg-links"}, state.scene);
    const nodesGroup = svgEl("g", {class: "dg-nodes"}, state.scene);
    const cardsGroup = svgEl("g", {class: "dg-details"}, state.scene);
    const nodeElements = {}, edgeElements = [], linkElements = [], connectors = [];

    for (const nodeId of ids) {
      const node = evaluation.nodes[nodeId];
      if (!node.parent || !starts[node.parent]) continue;
      const element = svgEl("path", {class: "dg-edge dg-edge-" + node.status, "data-from": node.parent, "data-to": nodeId}, edges);
      edgeElements.push({element, from: node.parent, to: nodeId});
    }

    let lane = 0;
    for (const link of evaluation.links) {
      if (!positions[link.from] || !positions[link.to]) continue;
      const active = state.selected === link.from || state.selected === link.to;
      if (!active) continue;
      const path = svgEl("path", {class: "dg-link dg-link-active", "marker-end": "url(#dg-arrow)", "data-from": link.from, "data-to": link.to}, links);
      linkElements.push({element: path, from: link.from, to: link.to, lane: lane++});
      svgEl("title", {}, path).textContent = link.from + " → " + link.to + (link.label ? ": " + link.label : "");
    }

    for (const nodeId of ids) {
      const node = evaluation.nodes[nodeId];
      const position = positions[nodeId] || before[nodeId];
      const classes = ["dg-node", "dg-node-" + node.status];
      if (position.depth === 0) classes.push("dg-node-root");
      if (state.selected === nodeId) classes.push("dg-node-selected");
      if (node.ownStatus === "no_data" && node.evaluator !== "aggregate") classes.push("dg-node-missing");
      const group = svgEl("g", {class: classes.join(" "), transform: "translate(" + position.x + "," + position.y + ")", tabindex: 0, role: "button", "data-node-id": nodeId, "aria-label": node.label + ", " + statusLabel(node.status)}, nodesGroup);
      nodeElements[nodeId] = group;
      if (!positions[nodeId]) {
        group.style.pointerEvents = "none";
        group.setAttribute("tabindex", "-1");
      }
      const fill = scoreColor(node.score);
      const isRoot = position.depth === 0;
      group.setAttribute("aria-expanded", String(state.detailsId === nodeId));
      if (node.children.length) group.setAttribute("data-children-expanded", String(expanded.has(nodeId)));
      // A compact hit area includes the wrapped label, never a sibling's space.
      const labelWidth = isRoot ? position.radius * 2 : Math.max(72, ...position.lines.map((line) => line.length * 8));
      svgEl("rect", {class: "dg-hit", x: -labelWidth / 2 - 4, y: -position.radius - 4, width: labelWidth + 8, height: position.radius * 2 + 8 + (isRoot ? 0 : 10 + position.lines.length * LAYOUT.labelLineHeight), rx: 8}, group);
      const circle = svgEl("circle", {r: position.radius, class: "dg-circle"}, group);
      if (fill) circle.style.fill = fill;
      const hiddenChildren = node.children.length && !expanded.has(nodeId) ? node.children.length : 0;
      const lineHeight = isRoot ? 24 : LAYOUT.labelLineHeight;
      const label = svgEl("text", {class: "dg-label" + (isRoot ? " dg-label-root" : ""), "text-anchor": "middle"}, group);
      const labelY = isRoot ? -(position.lines.length - 1) * lineHeight / 2 + 7 : position.radius + 22;
      position.lines.forEach((line, index) => {
        svgEl("tspan", {x: 0, y: labelY + index * lineHeight}, label).textContent = line;
      });
      if (hiddenChildren) {
        const badge = svgEl("text", {class: "dg-badge", x: position.radius, y: -position.radius, dy: "0.35em", "text-anchor": "middle"}, group);
        badge.textContent = "+" + hiddenChildren;
      }
      const tooltip = [node.label + " — " + statusLabel(node.status)]
        .concat(node.reasons.slice(0, 3))
        .concat(node.hints.slice(0, 2).map((hint) => "Hint: " + hint));
      svgEl("title", {}, group).textContent = tooltip.join("\n");
      group.addEventListener("click", () => selectNode(state, nodeId, true));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectNode(state, nodeId, true);
        }
      });
    }

    for (const [id, card] of state.cards) {
      card.panel.inert = state.detailsId !== id;
      card.element.dataset.closing = String(state.detailsId !== id);
      cardsGroup.appendChild(card.element);
      connectors.push({id, element: svgEl("path", {class: "dg-edge dg-detail-connector"}, edges)});
    }
    const paint = (progress) => {
      const framePositions = {}, opacity = {};
      for (const id of ids) {
        const start = starts[id], end = ends[id];
        const p = {...end};
        for (const key of ["x", "y", "cardHeight", "cardWidth", "cardOffset"]) p[key] = (start[key] || 0) + ((end[key] || 0) - (start[key] || 0)) * progress;
        framePositions[id] = p;
        const initialOpacity = before[id] ? (beforeOpacity[id] ?? 1) : 0;
        opacity[id] = initialOpacity + ((positions[id] ? 1 : 0) - initialOpacity) * progress;
        nodeElements[id].setAttribute("transform", "translate(" + p.x + "," + p.y + ")");
        nodeElements[id].style.opacity = opacity[id];
      }
      // Hold the clicked node in screen space without changing zoom. Incremental
      // adjustments also compose with wheel zoom and drag during the animation.
      const previous = state.displayPositions && state.displayPositions[state.selected];
      const current = framePositions[state.selected];
      if (!state.autoFit && previous && current) {
        state.view.x += (previous.x - current.x) * state.view.scale;
        state.view.y += (previous.y - current.y) * state.view.scale;
      }
      state.displayPositions = framePositions;
      state.displayOpacity = opacity;
      for (const edge of edgeElements) {
        edge.element.setAttribute("d", edgePath(framePositions[edge.from], framePositions[edge.to]));
        edge.element.style.opacity = Math.min(opacity[edge.from], opacity[edge.to]);
      }
      for (const link of linkElements) {
        const route = causeRoute(framePositions[link.from], framePositions[link.to], framePositions, link.lane);
        link.element.setAttribute("d", roundedPath(route));
        link.element.style.opacity = Math.min(opacity[link.from], opacity[link.to]);
      }
      for (const [id, card] of state.cards) {
        const p = framePositions[id];
        if (!p) continue;
        card.element.setAttribute("x", p.x - card.width / 2);
        card.element.setAttribute("y", p.y + p.cardOffset);
        card.element.setAttribute("height", Math.max(0, p.cardHeight));
        // Clip the HTML box, not foreignObject: Chromium otherwise rejects
        // pointer hits on its buttons after zoom, even with an inset of zero.
        card.panel.style.clipPath = p.cardWidth >= card.width ? "none" : "inset(0 " + Math.max(0, (card.width - p.cardWidth) / 2) + "px)";
        card.element.style.opacity = Math.min(1, p.cardHeight / card.height);
      }
      for (const connector of connectors) {
        const p = framePositions[connector.id];
        if (!p) continue;
        connector.element.setAttribute("d", "M" + p.x + "," + (p.y + p.cardOffset - 18) + " V" + (p.y + p.cardOffset));
        connector.element.style.opacity = Math.min(1, p.cardHeight / 30);
      }
      applyView(state);
    };
    const finish = () => {
      paint(1);
      for (const id of ids) if (!positions[id]) nodeElements[id].remove();
      for (const edge of edgeElements) if (!positions[edge.to]) edge.element.remove();
      for (const [id, card] of state.cards) {
        if (state.detailsId === id) continue;
        if (card.observer) card.observer.disconnect();
        card.element.remove();
        state.cards.delete(id);
      }
      for (const connector of connectors) if (!state.cards.has(connector.id)) connector.element.remove();
      state.displayPositions = positions;
      state.frame = null;
      svg.dataset.animating = "false";
    };
    const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animate === false || !Object.keys(before).length || reduced) finish();
    else {
      svg.dataset.animating = "true";
      paint(0);
      const startTime = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - startTime) / MOTION_MS);
        if (t >= 1) { finish(); return; }
        paint(t * t * (3 - 2 * t));
        state.frame = requestAnimationFrame(step);
      };
      state.frame = requestAnimationFrame(step);
    }
  }

  function selectNode(state, nodeId, toggle) {
    const node = state.evaluation.nodes[nodeId];
    if (!node) return;
    const focused = document.activeElement && document.activeElement.getAttribute("data-node-id") === nodeId;
    let ancestor = node.parent;
    while (ancestor) {
      state.expanded.add(ancestor);
      ancestor = state.evaluation.nodes[ancestor].parent;
    }
    const closing = toggle && state.detailsId === nodeId;
    if (node.children.length && toggle) {
      if (closing) state.expanded.delete(nodeId);
      else state.expanded.add(nodeId);
    }
    state.selected = nodeId;
    state.detailsId = closing ? null : nodeId;
    state.autoFit = false;
    drawGraph(state);
    if (focused) {
      const selected = state.svg.querySelector(".dg-node-selected");
      if (selected) selected.focus({preventScroll: true});
    }
  }

  function drawPanel(state, nodeId, panel) {
    const {evaluation} = state;
    panel.innerHTML = "";
    const node = evaluation.nodes[nodeId];
    const head = el("div", "dg-panel-head", panel);
    const badge = el("span", "dg-status dg-status-" + node.status, head, statusLabel(node.status));
    const fill = scoreColor(node.score);
    if (fill) badge.style.background = fill;
    el("h3", "dg-panel-title", head, node.label);
    el("code", "dg-panel-id", head, node.id);
    const close = el("button", "dg-panel-close", head, "×");
    close.type = "button";
    close.setAttribute("aria-label", "Close node details");
    close.addEventListener("click", () => {
      selectNode(state, nodeId, true);
      state.svg.querySelector(".dg-node-selected").focus({preventScroll: true});
    });
    if (node.summary) el("p", "dg-panel-summary", panel, node.summary);
    if (node.ownScore === null && node.score !== null) {
      el("p", "dg-panel-note", panel, "This node has no evidence of its own; the color comes from its children.");
    } else if (node.childScore !== null && node.childScore > node.ownScore) {
      el("p", "dg-panel-note", panel, "The stronger warning in this branch comes from its children, not this node's own evidence.");
    }
    if (node.error) el("p", "dg-panel-error", panel, "Evaluator error: " + node.error);

    if (node.reasons.length) {
      el("h4", "dg-panel-h", panel, "Why");
      const list = el("ul", "dg-reasons", panel);
      for (const reason of node.reasons) el("li", null, list, reason);
    }
    const factKeys = Object.keys(node.facts);
    if (factKeys.length) {
      el("h4", "dg-panel-h", panel, "Facts");
      const table = el("table", "dg-facts", panel);
      for (const key of factKeys) {
        const row = el("tr", null, table);
        el("th", null, row, key);
        el("td", null, row, node.facts[key]);
      }
    }
    if (node.hints.length) {
      el("h4", "dg-panel-h", panel, "Missing data");
      const list = el("ul", "dg-hints", panel);
      for (const hint of node.hints) el("li", null, list, hint);
    }
    if (node.causes.length || node.causedBy.length) {
      el("h4", "dg-panel-h", panel, "Related causes");
      const list = el("ul", "dg-causes", panel);
      for (const cause of node.causes) {
        const item = el("li", null, list);
        item.appendChild(document.createTextNode("→ "));
        nodeButton(state, item, cause.to);
        if (cause.label) item.appendChild(document.createTextNode(" — " + cause.label));
      }
      for (const cause of node.causedBy) {
        const item = el("li", null, list);
        item.appendChild(document.createTextNode("← "));
        nodeButton(state, item, cause.from);
        if (cause.label) item.appendChild(document.createTextNode(" — " + cause.label));
      }
    }
    if (node.children.length) {
      el("h4", "dg-panel-h", panel, "Children");
      const list = el("ul", "dg-children", panel);
      for (const childId of node.children) {
        const child = evaluation.nodes[childId];
        const item = el("li", null, list);
        const dot = el("span", "dg-dot dg-dot-" + child.status, item);
        const color = scoreColor(child.score);
        if (color) dot.style.background = color;
        nodeButton(state, item, childId);
        item.appendChild(document.createTextNode(" " + statusLabel(child.status)));
      }
    }

    el("h4", "dg-panel-h", panel, "Report items (" + node.present + " of " + node.bindings.length + " with data)");
    const groups = [["present", "with data"], ["empty", "empty"], ["skipped", "skipped"], ["unsupported", "unsupported"], ["error", "error"], ["absent", "not in this report"]];
    for (const [presence, title] of groups) {
      const bindings = node.bindings.filter((binding) => binding.presence === presence);
      if (!bindings.length) continue;
      el("div", "dg-items-title", panel, title);
      const list = el("div", "dg-items", panel);
      for (const binding of bindings) {
        const chip = el("button", "dg-item dg-item-" + presence + " dg-item-role-" + binding.role, list);
        chip.type = "button";
        chip.dataset.itemId = binding.id;
        el("span", "dg-item-title", chip, binding.title);
        el("code", "dg-item-id", chip, binding.id);
        const meta = [binding.role];
        if (binding.rows !== null && binding.rows !== undefined) meta.push(binding.rows + " rows");
        if (binding.kind === "chart") meta.push("chart");
        if (binding.collection_status && binding.collection_status !== "ok") meta.push(binding.collection_status);
        el("span", "dg-item-meta", chip, meta.join(" · "));
        if (presence === "absent") {
          chip.disabled = true;
          chip.title = "This item is not part of the current report";
        } else {
          chip.title = "Scroll the report to " + binding.id;
          chip.addEventListener("click", () => {
            if (typeof state.onItemClick === "function") state.onItemClick(binding.id, binding);
          });
        }
      }
    }
  }

  function nodeButton(state, parent, nodeId) {
    const node = state.evaluation.nodes[nodeId];
    const button = el("button", "dg-node-link", parent, node ? node.label : nodeId);
    button.type = "button";
    button.addEventListener("click", () => {
      let cursor = node ? node.parent : null;
      while (cursor) {
        state.expanded.add(cursor);
        cursor = state.evaluation.nodes[cursor].parent;
      }
      selectNode(state, nodeId, false);
      const position = state.displayPositions[nodeId] || state.positions[nodeId];
      if (position) {
        const size = viewportSize(state);
        state.view.x = size.width / 2 - position.x * state.view.scale;
        state.view.y = size.height / 2 - position.y * state.view.scale;
        state.autoFit = false;
        applyView(state);
      }
    });
    return button;
  }

  function drawHeader(state) {
    const {evaluation, header} = state;
    header.innerHTML = "";
    const coverage = evaluation.coverage;
    const titleRow = el("div", "dg-title-row", header);
    el("h2", "dg-title", titleRow, "Diagnostic graph");
    const expandAll = el("button", "dg-toggle", titleRow, "Expand all");
    expandAll.type = "button";
    expandAll.addEventListener("click", () => {
      const allExpanded = evaluation.order.every((nodeId) => !evaluation.nodes[nodeId].children.length || state.expanded.has(nodeId));
      if (allExpanded) {
        state.expanded = initialExpanded(evaluation);
        state.detailsId = null;
        expandAll.textContent = "Expand all";
      } else {
        for (const nodeId of evaluation.order) state.expanded.add(nodeId);
        expandAll.textContent = "Collapse";
      }
      drawGraph(state);
      fitView(state);
    });
    const toggle = el("button", "dg-toggle", titleRow, state.collapsed ? "Show" : "Hide");
    toggle.type = "button";
    toggle.addEventListener("click", () => {
      state.collapsed = !state.collapsed;
      writeCollapsed(state.collapsed);
      state.body.hidden = state.collapsed;
      toggle.textContent = state.collapsed ? "Show" : "Hide";
      if (!state.collapsed && state.autoFit) fitView(state);
    });
    const summary = el("p", "dg-summary", header);
    const parts = [];
    parts.push(coverage.rootsWithData + " of " + evaluation.roots.length + " roots have data");
    parts.push(coverage.statusCounts.crit + " critical node(s), " + coverage.statusCounts.warn + " warning node(s), " + coverage.statusCounts.no_data + " node(s) without data");
    parts.push(coverage.presentItems + " of " + coverage.boundItems + " bound items carry data (" + (coverage.runMode || "unknown") + " run, " + (coverage.collectionMode || "unknown") + " collection)");
    summary.textContent = parts.join(" · ");
    const missingModes = [];
    if (coverage.runMode !== "snapshots") missingModes.push("snapshots mode adds charts, rates and per-process CPU/I/O evidence");
    if (coverage.collectionMode === "remote-db-only") missingModes.push("local or remote mode adds host CPU, memory, disk and security evidence");
    if (missingModes.length) el("p", "dg-summary dg-summary-hint", header, "To light up grey nodes: " + missingModes.join("; ") + ".");
    const legend = el("div", "dg-legend", header);
    for (const [status, label] of [["ok", "OK"], ["warn", "Warning"], ["crit", "Critical"], ["no_data", "No data"]]) {
      const entry = el("span", "dg-legend-entry", legend);
      const dot = el("span", "dg-dot dg-dot-" + status, entry);
      const color = scoreColor({ok: 0.05, warn: 0.5, crit: 0.95}[status]);
      if (color) dot.style.background = color;
      entry.appendChild(document.createTextNode(label));
    }
    const entry = el("span", "dg-legend-entry", legend);
    el("span", "dg-legend-link", entry);
    entry.appendChild(document.createTextNode("cause links — shown for the selected node"));
    const badgeEntry = el("span", "dg-legend-entry", legend);
    el("span", "dg-legend-badge", badgeEntry, "+3");
    badgeEntry.appendChild(document.createTextNode("collapsed children — click a node for details; click again to close"));
  }

  function render(container, evaluation, options) {
    const opts = options || {};
    const previous = instances.get(container);
    if (previous) previous.destroy();
    container.innerHTML = "";
    container.classList.add("dg");
    const state = {
      evaluation,
      expanded: initialExpanded(evaluation),
      selected: null,
      detailsId: null,
      cards: new Map(),
      // Start at a readable size. Fitting a wide forest on load makes every
      // label microscopic; the explicit Fit control provides that overview.
      view: {x: 24, y: 48, scale: 0.8},
      autoFit: false,
      onItemClick: opts.onItemClick,
      collapsed: typeof opts.collapsed === "boolean" ? opts.collapsed : readCollapsed()
    };
    state.header = el("div", "dg-header", container);
    state.body = el("div", "dg-body", container);
    state.canvas = el("div", "dg-canvas", state.body);
    state.svg = svgEl("svg", {class: "dg-svg", role: "group", tabindex: 0, "aria-label": "Diagnostic graph. Drag to pan, scroll or use plus and minus to zoom. Home fits the graph."}, state.canvas);
    state.measurer = el("div", "dg-measurer", state.canvas);
    state.measurer.style.width = DETAIL_WIDTH + "px";
    state.measurer.setAttribute("aria-hidden", "true");
    state.measurer.inert = true;
    state.body.hidden = state.collapsed;
    attachViewport(state);
    drawHeader(state);
    drawGraph(state, false);
    const controller = {
      select: (nodeId) => selectNode(state, nodeId, false),
      expandAll: () => {
        for (const nodeId of evaluation.order) state.expanded.add(nodeId);
        drawGraph(state);
        fitView(state);
      },
      fit: () => fitView(state),
      destroy: () => {
        if (state.frame) cancelAnimationFrame(state.frame);
        state.frame = null;
        if (state.resizeObserver) state.resizeObserver.disconnect();
        for (const card of state.cards.values()) if (card.observer) card.observer.disconnect();
        instances.delete(container);
      },
      state
    };
    instances.set(container, controller);
    return controller;
  }

  return {render, scoreColor, layout, initialExpanded, truncateLabel, labelLines, nodeBounds, causeRoute, roundedPath, LAYOUT, DETAIL_WIDTH, MOTION_MS};
});
