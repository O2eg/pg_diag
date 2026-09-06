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
    rootRowGap: 128,
    levelHeight: 208,
    levelGap: 104,
    rootRadius: 120,
    radius: 72,
    radiusStep: 12,
    marginX: 24,
    marginTop: 24,
    marginBottom: 72,
    labelMaxChars: 50,
    labelWrapChars: 14,
    labelLineHeight: 18
  };
  const STORAGE_KEY = "pg-diag-graph-collapsed";
  const MIN_ZOOM = 0.01;
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

  function nodeStatusLabel(node) {
    return node.status === "no_data" && (node.present || (node.inputBindings || []).some(b => b.presence === "present")) ? "Not assessed" : statusLabel(node.status);
  }

  function truncateLabel(text, maxChars) {
    const chars = Array.from(String(text || ""));
    return chars.length > maxChars ? chars.slice(0, maxChars - 1).join("") + "…" : chars.join("");
  }

  function labelLines(text, maxChars) {
    const words = String(text || "").trim().split(/\s+/);
    const lines = [];
    let line = "";
    for (let word of words) {
      if (line && Array.from(line + " " + word).length > maxChars) {
        lines.push(line);
        line = "";
      }
      let chars = Array.from(word);
      while (chars.length > maxChars) {
        lines.push(chars.slice(0, maxChars).join(""));
        chars = chars.slice(maxChars);
      }
      word = chars.join("");
      line = line ? line + " " + word : word;
    }
    if (line) lines.push(line);
    return lines;
  }

  function fitNodeLabels(state) {
    for (const node of state.svg.querySelectorAll(".dg-node")) {
      const caption = node.querySelector(".dg-caption");
      const label = caption.querySelector(".dg-label");
      const badgeBox = caption.querySelector(".dg-node-badge");
      const radius = +node.querySelector(".dg-circle").getAttribute("r");
      if (badgeBox) {
        const badge = badgeBox.firstElementChild;
        const labelBox = label.getBBox();
        const width = badge.offsetWidth, height = badge.offsetHeight;
        badgeBox.setAttribute("x", -width / 2);
        badgeBox.setAttribute("y", labelBox.y + labelBox.height + 8);
        badgeBox.setAttribute("width", width);
        badgeBox.setAttribute("height", height);
      }
      const box = caption.getBBox();
      const extent = Math.hypot(box.width / 2, box.height / 2);
      const scale = Math.min(1, (radius - 12) / (extent || 1));
      caption.setAttribute("transform", "scale(" + scale + ") translate(" + -(box.x + box.width / 2) + "," + -(box.y + box.height / 2) + ")");
    }
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

  // Start with the six roots only; their colors still include hidden findings.
  function initialExpanded() {
    return new Set();
  }

  // Pack the occupied contours, not full-height rectangular subtree spans.
  // Include connecting gutters so a neighbour cannot move into an edge.
  function contourShift(left, right, gap) {
    let shift = 0;
    for (const a of left) for (const b of right) {
      if (a.top <= b.bottom && a.bottom >= b.top) shift = Math.max(shift, a.right + gap - b.left);
    }
    return shift;
  }

  function moveBoxes(boxes, x, y) {
    return boxes.map(b => ({left: b.left + x, right: b.right + x, top: b.top + y, bottom: b.bottom + y}));
  }

  // Children share a row; cards move only their own descendants. Health and
  // security stay below all visible resource trees and their detail cards.
  function layout(evaluation, expanded, detail) {
    const details = detail instanceof Map ? detail : new Map(detail ? [[detail.id, detail]] : []);
    const nodes = evaluation.nodes;
    const positions = {};
    const spans = {};
    const depths = {};
    const depthOf = id => depths[id] ?? (depths[id] = nodes[id].parent ? depthOf(nodes[id].parent) + 1 : 0);
    const rootRadius = Math.max(LAYOUT.rootRadius, ...evaluation.order.filter(id => nodes[id].kind !== "sources").map(id => LAYOUT.radius + depthOf(id) * LAYOUT.radiusStep));
    let maxBottom = 0;
    const childrenOf = (id) => expanded.has(id) ? nodes[id].children : [];
    const measure = (id, depth) => {
      const caption = truncateLabel(String(nodes[id].label || "").trim().replace(/\s+/g, " "), LAYOUT.labelMaxChars);
      const lines = labelLines(caption, LAYOUT.labelWrapChars);
      const radius = depth === 0 ? rootRadius : (rootRadius - depth * LAYOUT.radiusStep) / 1.5;
      const labelWidth = radius * 2;
      const labelBottom = radius + 4;
      const card = details.get(id);
      const cardHeight = card ? card.height : 0;
      const cardWidth = cardHeight ? card.width : 0;
      const cardOffset = labelBottom + 18;
      const children = childrenOf(id);
      const bottom = cardHeight ? cardOffset + cardHeight : labelBottom;
      children.forEach(child => measure(child, depth + 1));
      const childRadius = children.length ? spans[children[0]].radius : 0;
      const childY = Math.max(LAYOUT.levelHeight, bottom + childRadius + LAYOUT.levelGap);
      let contour = [];
      const offsets = [];
      for (const child of children) {
        const boxes = moveBoxes(spans[child].contour, 0, childY);
        const x = contourShift(contour, boxes, LAYOUT.siblingGap);
        offsets.push(x);
        contour.push(...moveBoxes(boxes, x, 0));
      }
      const centre = children.length ? (offsets[0] + offsets[offsets.length - 1]) / 2 : 0;
      contour = moveBoxes(contour, -centre, 0);
      const span = {offsets: offsets.map(x => x - centre), childY, lines, radius, labelWidth, cardHeight, cardWidth, cardOffset};
      const parent = {x: 0, y: 0, ...span};
      contour.push(nodeBounds(parent));
      for (const x of span.offsets) {
        const route = treeRoute(parent, {x, y: childY, radius: childRadius});
        for (let i = 1; i < route.length; i++) {
          const a = route[i - 1], b = route[i];
          contour.push({left: Math.min(a.x, b.x) - 8, right: Math.max(a.x, b.x) + 8,
            top: Math.min(a.y, b.y) - 8, bottom: Math.max(a.y, b.y) + 8});
        }
      }
      spans[id] = {...span, contour};
    };
    const place = (id, depth, x, y) => {
      const span = spans[id];
      const children = childrenOf(id);
      children.forEach((child, index) => place(child, depth + 1, x + span.offsets[index], y + span.childY));
      const {radius, labelWidth, cardHeight, cardWidth, cardOffset, lines} = span;
      positions[id] = {x, y, depth, radius, lines, labelWidth, cardHeight, cardWidth, cardOffset};
      maxBottom = Math.max(maxBottom, nodeBounds(positions[id]).bottom);
    };
    const lowerRoots = new Set(["database_health", "database_security"]);
    const rootRows = [
      evaluation.roots.filter(id => !lowerRoots.has(id)),
      evaluation.roots.filter(id => lowerRoots.has(id))
    ];
    let top = LAYOUT.marginTop;
    let width = LAYOUT.marginX * 2;
    for (const roots of rootRows) {
      if (!roots.length) continue;
      for (const id of roots) measure(id, 0);
      const contour = [], offsets = [];
      for (const id of roots) {
        const x = contourShift(contour, spans[id].contour, LAYOUT.treeGap);
        offsets.push(x);
        contour.push(...moveBoxes(spans[id].contour, x, 0));
      }
      const left = Math.min(...contour.map(b => b.left));
      roots.forEach((id, index) => place(id, 0, offsets[index] - left + LAYOUT.marginX, top + rootRadius));
      width = Math.max(width, Math.max(...contour.map(b => b.right)) - left + LAYOUT.marginX * 2);
      top = maxBottom + LAYOUT.rootRowGap;
    }
    return {positions, width, height: maxBottom + LAYOUT.marginBottom};
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
    state.centerCardId = null;
    const {width, height} = viewportSize(state);
    if (!width || !height || !state.bounds) return;
    const scale = Math.max(MIN_ZOOM, Math.min(1, (width - 48) / state.bounds.width, (height - 96) / state.bounds.height));
    state.view = {scale, x: (width - state.bounds.width * scale) / 2, y: 48 + (height - 96 - state.bounds.height * scale) / 2};
    state.autoFit = true;
    applyView(state);
  }

  function zoomAt(state, target, point) {
    state.centerCardId = null;
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

  function attachFullScreen(state, button) {
    const dialog = el("dialog", "dg-fullscreen", state.body);
    dialog.setAttribute("aria-label", "Diagnostic graph");
    let savedHeight, savedOverflow;
    const setFullScreen = (active) => {
      if (active === dialog.open) return;
      if (active) {
        // Keep the report's place while the canvas occupies the top layer.
        savedHeight = state.body.style.height;
        savedOverflow = document.documentElement.style.overflow;
        state.body.style.height = state.body.getBoundingClientRect().height + "px";
        document.documentElement.style.overflow = "hidden";
        dialog.appendChild(state.canvas);
        dialog.showModal();
      } else {
        state.body.insertBefore(state.canvas, dialog);
        dialog.close();
        state.body.style.height = savedHeight;
        document.documentElement.style.overflow = savedOverflow;
      }
      const label = active ? "Exit full screen" : "Full screen";
      button.textContent = label;
      button.title = label;
      button.setAttribute("aria-label", label);
      button.setAttribute("aria-pressed", String(active));
      button.focus({preventScroll: true});
    };
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => setFullScreen(!dialog.open));
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      setFullScreen(false);
    });
    state.exitFullScreen = () => setFullScreen(false);
  }

  function attachViewport(state) {
    const controls = el("div", "dg-zoom", state.canvas);
    controls.setAttribute("role", "group");
    controls.setAttribute("aria-label", "Graph controls");
    const button = (label, name, handler) => {
      const control = el("button", "dg-zoom-button", controls, label);
      control.type = "button";
      control.title = name;
      control.setAttribute("aria-label", name);
      if (handler) control.addEventListener("click", handler);
      return control;
    };
    state.expandAllButton = button("Expand all", "Expand all", () => setAllExpanded(state, true));
    button("Collapse all", "Collapse all", () => setAllExpanded(state, false));
    state.zoomOut = button("−", "Zoom out", () => zoomAt(state, state.view.scale / 1.4));
    state.zoomValue = el("output", "dg-zoom-value", controls);
    state.zoomValue.setAttribute("aria-label", "Zoom level");
    state.zoomIn = button("+", "Zoom in", () => zoomAt(state, state.view.scale * 1.4));
    button("Fit", "Fit graph", () => fitView(state));
    button("1:1", "Actual size", () => zoomAt(state, 1));
    attachFullScreen(state, button("Full screen", "Full screen"));
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
        state.centerCardId = null;
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
        state.centerCardId = null;
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
        fitNodeLabels(state);
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

  function treeRoute(from, to) {
    const start = {x: from.x, y: from.y + (from.cardHeight ? from.cardOffset + from.cardHeight : from.radius)};
    const end = {x: to.x, y: to.y - to.radius};
    if (start.x === end.x) return [start, end];
    const gutter = (start.y + end.y) / 2;
    return [start, {x: start.x, y: gutter}, {x: end.x, y: gutter}, end]
      .filter((p, i, points) => !i || p.x !== points[i - 1].x || p.y !== points[i - 1].y);
  }

  function nodeBounds(position) {
    const width = Math.max(position.labelWidth, position.cardHeight ? position.cardWidth : 0);
    return {left: position.x - width / 2 - 4, right: position.x + width / 2 + 4,
      top: position.y - position.radius - 4,
      bottom: position.y + (position.cardHeight ? position.cardOffset + position.cardHeight : position.radius + 4)};
  }

  // Route causes through level gutters and a free vertical lane. Only links
  // involving the selection are drawn, so unrelated branches stay legible.
  function causeRoute(from, to, positions, lane, allowDetour = true) {
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
    if (allowDetour && !causeRouteClear(compact, from, to, positions)) {
      return causeDetour(from, to, positions) || compact;
    }
    return compact;
  }

  // Several open cards can cut across the old level gutters. Search their
  // rectilinear visibility grid only when the short gutter route is blocked.
  // The extra clearance also keeps rounded corners outside the obstacles.
  function causeDetour(from, to, positions) {
    const side = to.x >= from.x ? 1 : -1;
    const start = {x: from.x + side * (from.radius + 16), y: from.y};
    const end = {x: to.x, y: to.y - to.radius - 28};
    const boxes = routingObstacles(positions).map(b => ({left: b.left - 8, right: b.right + 8,
      top: b.top - 8, bottom: b.bottom + 8}));
    const xs = [...new Set([start.x, end.x, ...boxes.flatMap(b => [b.left, b.right])])].sort((a, b) => a - b);
    const ys = [...new Set([start.y, end.y, ...boxes.flatMap(b => [b.top, b.bottom])])].sort((a, b) => a - b);
    const width = xs.length, size = width * ys.length;
    const startId = ys.indexOf(start.y) * width + xs.indexOf(start.x);
    const endId = ys.indexOf(end.y) * width + xs.indexOf(end.x);
    const distance = new Float64Array(size).fill(Infinity), previous = new Int32Array(size).fill(-1);
    const heap = [];
    const push = entry => {
      let i = heap.length;
      heap.push(entry);
      while (i && heap[(i - 1) >> 1].priority > entry.priority) {
        heap[i] = heap[(i - 1) >> 1]; i = (i - 1) >> 1;
      }
      heap[i] = entry;
    };
    const pop = () => {
      const first = heap[0], last = heap.pop();
      if (heap.length) {
        let i = 0;
        while (i * 2 + 1 < heap.length) {
          let child = i * 2 + 1;
          if (child + 1 < heap.length && heap[child + 1].priority < heap[child].priority) child++;
          if (heap[child].priority >= last.priority) break;
          heap[i] = heap[child]; i = child;
        }
        heap[i] = last;
      }
      return first;
    };
    distance[startId] = 0;
    push({id: startId, distance: 0, priority: 0});
    while (heap.length) {
      const current = pop(), id = current.id;
      if (current.distance !== distance[id]) continue;
      if (id === endId) break;
      const ix = id % width, iy = Math.floor(id / width), x = xs[ix], y = ys[iy];
      const neighbours = [];
      if (ix) neighbours.push(id - 1);
      if (ix + 1 < width) neighbours.push(id + 1);
      if (iy) neighbours.push(id - width);
      if (iy + 1 < ys.length) neighbours.push(id + width);
      for (const next of neighbours) {
        const nx = xs[next % width], ny = ys[Math.floor(next / width)];
        const candidate = current.distance + Math.abs(nx - x) + Math.abs(ny - y);
        if (candidate >= distance[next]) continue;
        if (boxes.some(b => x === nx
          ? x > b.left && x < b.right && Math.max(y, ny) > b.top && Math.min(y, ny) < b.bottom
          : y > b.top && y < b.bottom && Math.max(x, nx) > b.left && Math.min(x, nx) < b.right)) continue;
        distance[next] = candidate; previous[next] = id;
        push({id: next, distance: candidate, priority: candidate + Math.abs(nx - end.x) + Math.abs(ny - end.y)});
      }
    }
    if (!Number.isFinite(distance[endId])) return null;
    const route = [];
    for (let id = endId; id !== -1; id = previous[id]) route.push({x: xs[id % width], y: ys[Math.floor(id / width)]});
    route.reverse();
    route.unshift({x: from.x + side * from.radius, y: from.y});
    route.push({x: to.x, y: to.y - to.radius - 6});
    return route.filter((p, i) => !i || i === route.length - 1 ||
      !((route[i - 1].x === p.x && p.x === route[i + 1].x) || (route[i - 1].y === p.y && p.y === route[i + 1].y)));
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

  // During a transition, the retiring card and moving subtrees can occupy
  // a gutter which is clear in the final layout. Do not paint a cause through
  // them. Check every segment, including the horizontal approach to a node.
  function routingObstacles(positions) {
    const boxes = [];
    for (const p of Object.values(positions)) {
      boxes.push({...nodeBounds({...p, cardHeight: 0}), position: p, card: false});
      if (p.cardHeight > 0 && p.cardWidth > 0) boxes.push({
        left: p.x - p.cardWidth / 2 - 8, right: p.x + p.cardWidth / 2 + 8,
        top: p.y + p.cardOffset - 8, bottom: p.y + p.cardOffset + p.cardHeight + 8,
        position: p, card: true
      });
    }
    return boxes;
  }

  function causeRouteClear(points, from, to, positions, treeEdge, obstacles) {
    // A disappearing child can retract above the bottom of its parent's
    // closing card. Never draw the upward remainder back through that card.
    if (treeEdge && points[points.length - 1].y < points[0].y) return false;
    const crosses = (a, b, box) => a.x === b.x
      ? a.x > box.left && a.x < box.right && Math.max(a.y, b.y) > box.top && Math.min(a.y, b.y) < box.bottom
      : a.y > box.top && a.y < box.bottom && Math.max(a.x, b.x) > box.left && Math.min(a.x, b.x) < box.right;
    const boxes = obstacles || routingObstacles(positions);
    return points.every((point, index) => Number.isFinite(point.x) && Number.isFinite(point.y)
      && (!index || !boxes.some(box => (box.card ? !(treeEdge && box.position === from)
        : box.position !== from && box.position !== to) && crosses(points[index - 1], point, box))));
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
        if (state.openDetails.has(nodeId) && height > 0 && height !== card.height) {
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
    const visible = new Set();
    const visit = id => {
      visible.add(id);
      if (expanded.has(id)) evaluation.nodes[id].children.forEach(visit);
    };
    evaluation.roots.forEach(visit);
    const details = new Map();
    for (const id of state.openDetails) {
      if (visible.has(id)) details.set(id, ensureCard(state, id));
      else state.openDetails.delete(id);
    }
    const target = layout(evaluation, expanded, details);
    const treeExpanded = evaluation.order.every(id => !evaluation.nodes[id].children.length || expanded.has(id));
    state.expandAllButton.title = treeExpanded ? "Expand all node details" : "Expand all branches";
    state.expandAllButton.disabled = treeExpanded && evaluation.order.every(id => state.openDetails.has(id));
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
      const related = link.kind === "related";
      const path = svgEl("path", {class: "dg-link dg-link-active", "marker-end": related ? null : "url(#dg-arrow)", "data-from": link.from, "data-to": link.to, "data-kind": related ? "related" : "cause"}, links);
      linkElements.push({element: path, from: link.from, to: link.to, lane: lane++});
      svgEl("title", {}, path).textContent = evaluation.nodes[link.from].label + (related ? " ↔ " : " → possible cause: ") + evaluation.nodes[link.to].label + (link.label ? ": " + link.label : "");
    }

    for (const nodeId of ids) {
      const node = evaluation.nodes[nodeId];
      const position = positions[nodeId] || before[nodeId];
      const classes = ["dg-node", "dg-node-" + node.status];
      if (position.depth === 0) classes.push("dg-node-root");
      if (state.selected === nodeId) classes.push("dg-node-selected");
      if (node.ownStatus === "no_data" && node.evaluator !== "aggregate") classes.push("dg-node-missing");
      const group = svgEl("g", {class: classes.join(" "), transform: "translate(" + position.x + "," + position.y + ")", tabindex: 0, role: "button", "data-node-id": nodeId, "aria-label": node.label + ", " + nodeStatusLabel(node)}, nodesGroup);
      nodeElements[nodeId] = group;
      if (!positions[nodeId]) {
        group.style.pointerEvents = "none";
        group.setAttribute("tabindex", "-1");
      }
      const fill = scoreColor(node.score);
      const isRoot = position.depth === 0;
      group.setAttribute("aria-expanded", String(state.openDetails.has(nodeId)));
      if (node.children.length) group.setAttribute("data-children-expanded", String(expanded.has(nodeId)));
      svgEl("circle", {class: "dg-hit", r: position.radius + 4}, group);
      const circle = svgEl("circle", {r: position.radius, class: "dg-circle"}, group);
      if (fill) circle.style.fill = fill;
      const hiddenChildren = node.children.length && !expanded.has(nodeId) ? node.children.length : 0;
      const lineHeight = isRoot ? 48 : LAYOUT.labelLineHeight;
      const caption = svgEl("g", {class: "dg-caption"}, group);
      const label = svgEl("text", {class: "dg-label" + (isRoot ? " dg-label-root" : ""), "text-anchor": "middle"}, caption);
      const labelY = -(position.lines.length - 1) * lineHeight / 2;
      label.setAttribute("dominant-baseline", "central");
      position.lines.forEach((line, index) => {
        svgEl("tspan", {x: 0, y: labelY + index * lineHeight}, label).textContent = line;
      });
      if (hiddenChildren) {
        const badgeBox = svgEl("foreignObject", {class: "dg-node-badge", width: position.radius * 2, height: 48, "aria-hidden": "true"}, caption);
        el("span", "badge neutral dg-badge", badgeBox, "+" + hiddenChildren);
        group.setAttribute("aria-label", node.label + ", " + nodeStatusLabel(node) + ", " + hiddenChildren + " collapsed children");
      }
      const tooltip = [node.label + " — " + nodeStatusLabel(node)]
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

    // Measure outside animation frames; resize also handles initially hidden SVGs.
    fitNodeLabels(state);
    for (const [id, card] of state.cards) {
      card.panel.inert = !details.has(id);
      card.element.dataset.closing = String(!details.has(id));
      cardsGroup.appendChild(card.element);
      connectors.push({id, element: svgEl("path", {class: "dg-edge dg-detail-connector"}, edges)});
    }
    const centerId = state.centerCardId;
    const centered = positions[centerId], origin = starts[centerId];
    const viewport = viewportSize(state);
    const pan = centered && centered.cardHeight ? {
      x: viewport.width / 2 - state.view.x - origin.x * state.view.scale,
      y: viewport.height / 2 - state.view.y - (origin.y + centered.cardOffset + centered.cardHeight / 2) * state.view.scale
    } : null;
    let panProgress = 0;
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
      // Compensate for the selected node's layout movement before the card pan.
      // Incremental offsets preserve manual zoom and drag during the animation.
      const previous = (state.displayPositions && state.displayPositions[state.selected]) || (pan ? origin : null);
      const current = framePositions[state.selected];
      if (!state.autoFit && previous && current) {
        state.view.x += (previous.x - current.x) * state.view.scale;
        state.view.y += (previous.y - current.y) * state.view.scale;
      }
      // Use the same eased progress as the card, without a second animation.
      // Manual pan/zoom cancels this extra movement while relayout continues.
      if (pan && state.centerCardId === centerId) {
        state.view.x += pan.x * (progress - panProgress);
        state.view.y += pan.y * (progress - panProgress);
        panProgress = progress;
      }
      state.displayPositions = framePositions;
      state.displayOpacity = opacity;
      const obstacles = routingObstacles(framePositions);
      for (const edge of edgeElements) {
        const from = framePositions[edge.from], to = framePositions[edge.to];
        const route = treeRoute(from, to);
        edge.element.setAttribute("d", roundedPath(route));
        edge.element.style.opacity = causeRouteClear(route, from, to, framePositions, true, obstacles)
          ? Math.min(opacity[edge.from], opacity[edge.to]) : 0;
      }
      for (const link of linkElements) {
        const route = causeRoute(framePositions[link.from], framePositions[link.to], framePositions, link.lane, progress === 1);
        link.element.setAttribute("d", roundedPath(route));
        const clear = causeRouteClear(route, framePositions[link.from], framePositions[link.to], framePositions, false, obstacles);
        link.element.style.opacity = clear ? Math.min(opacity[link.from], opacity[link.to]) : 0;
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
        if (details.has(id)) continue;
        if (card.observer) card.observer.disconnect();
        card.element.remove();
        state.cards.delete(id);
      }
      for (const connector of connectors) if (!state.cards.has(connector.id)) connector.element.remove();
      state.displayPositions = positions;
      if (state.centerCardId === centerId) state.centerCardId = null;
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
    const closing = toggle && state.openDetails.has(nodeId);
    if (node.children.length && toggle) {
      if (closing) state.expanded.delete(nodeId);
      else state.expanded.add(nodeId);
    }
    state.selected = nodeId;
    if (!state.multipleDetails) state.openDetails.clear();
    if (closing) state.openDetails.delete(nodeId);
    else state.openDetails.add(nodeId);
    state.centerCardId = closing ? null : nodeId;
    state.autoFit = false;
    drawGraph(state);
    if (focused) {
      const selected = state.svg.querySelector(".dg-node-selected");
      if (selected) selected.focus({preventScroll: true});
    }
  }

  function setAllExpanded(state, expanded) {
    state.centerCardId = null;
    if (expanded && state.evaluation.order.every(id => !state.evaluation.nodes[id].children.length || state.expanded.has(id))) {
      state.multipleDetails = true;
      state.openDetails = new Set(state.evaluation.order);
    }
    state.expanded = expanded ? new Set(state.evaluation.order) : initialExpanded();
    if (!expanded) {
      state.selected = null;
      state.openDetails.clear();
      state.multipleDetails = false;
    }
    drawGraph(state);
    fitView(state);
  }

  function drawPanel(state, nodeId, panel) {
    const {evaluation} = state;
    panel.innerHTML = "";
    const node = evaluation.nodes[nodeId];
    const head = el("div", "dg-panel-head", panel);
    const badge = el("span", "dg-status dg-status-" + node.status, head, nodeStatusLabel(node));
    const fill = scoreColor(node.score);
    if (fill) badge.style.background = fill;
    el("h3", "dg-panel-title", head, node.label);
    el("code", "dg-panel-id", head, node.id);
    const close = el("button", "dg-panel-close", head, "×");
    close.type = "button";
    close.setAttribute("aria-label", "Close node details");
    close.addEventListener("click", () => {
      if (state.multipleDetails) {
        state.centerCardId = null;
        state.openDetails.delete(nodeId);
        state.selected = nodeId;
        state.autoFit = false;
        drawGraph(state);
      } else selectNode(state, nodeId, true);
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
      el("h4", "dg-panel-h", panel, "Assessment limits");
      const list = el("ul", "dg-hints", panel);
      for (const hint of node.hints) el("li", null, list, hint);
    }
    const related = node.causes.concat(node.causedBy).filter(link => link.kind === "related");
    for (const [heading, arrow, links] of [
      ["Possible causes", "→ ", node.causes.filter(link => link.kind !== "related")],
      ["Possible effects", "← ", node.causedBy.filter(link => link.kind !== "related")],
      ["Related checks", "↔ ", related]
    ]) {
      if (!links.length) continue;
      el("h4", "dg-panel-h", panel, heading);
      const list = el("ul", "dg-causes", panel);
      for (const link of links) {
        const item = el("li", null, list);
        item.appendChild(document.createTextNode(arrow));
        nodeButton(state, item, link.to || link.from);
        if (link.label) item.appendChild(document.createTextNode(" — " + link.label));
      }
    }
    if (node.bindings.length) el("h4", "dg-panel-h", panel, "Report items (" + node.present + " of " + node.bindings.length + " with data)");
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
        // Reuse the report's icon and type fallback for empty/failed items too.
        const icons = document.getElementById("item-" + binding.id)
          ?.querySelector(":scope > summary .data-type-icons");
        if (icons) chip.appendChild(icons.cloneNode(true));
        if (presence === "absent") {
          chip.disabled = true;
          chip.title = "This item is not part of the current report";
        } else {
          chip.title = "Scroll the report to " + binding.id;
          chip.addEventListener("click", () => {
            state.exitFullScreen();
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
    // Selection opens hidden ancestors and animates the card into view.
    // A second viewport adjustment here would invalidate that animation's pan.
    button.addEventListener("click", () => selectNode(state, nodeId, false));
    return button;
  }

  function drawHeader(state) {
    const {evaluation, header} = state;
    header.innerHTML = "";
    const coverage = evaluation.coverage;
    const titleRow = el("div", "dg-title-row", header);
    el("h2", "dg-title", titleRow, "Diagnostic graph");
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
    parts.push(coverage.statusCounts.crit + " critical node(s), " + coverage.statusCounts.warn + " warning node(s), " + coverage.statusCounts.no_data + " node(s) without assessment");
    parts.push(coverage.presentItems + " of " + coverage.boundItems + " bound items carry data (" + (coverage.runMode || "unknown") + " run, " + (coverage.collectionMode || "unknown") + " collection)");
    summary.textContent = parts.join(" · ");
    const missingModes = [];
    if (coverage.runMode !== "snapshots") missingModes.push("snapshots mode adds charts, rates and per-process CPU/I/O evidence");
    if (coverage.collectionMode === "remote-db-only") missingModes.push("local or remote mode adds host CPU, memory, disk and security evidence");
    if (missingModes.length) el("p", "dg-summary dg-summary-hint", header, "To light up grey nodes: " + missingModes.join("; ") + ".");
    const legend = el("div", "dg-legend", header);
    for (const [status, label] of [["ok", "OK"], ["warn", "Warning"], ["crit", "Critical"], ["no_data", "Not assessed / no data"]]) {
      const entry = el("span", "dg-legend-entry", legend);
      const dot = el("span", "dg-dot dg-dot-" + status, entry);
      const color = scoreColor({ok: 0.05, warn: 0.5, crit: 0.95}[status]);
      if (color) dot.style.background = color;
      entry.appendChild(document.createTextNode(label));
    }
    const entry = el("span", "dg-legend-entry", legend);
    el("span", "dg-legend-link", entry);
    entry.appendChild(document.createTextNode("arrows → possible causes; lines without arrows: related checks — selected node only"));
    const badgeEntry = el("span", "dg-legend-entry", legend);
    el("span", "badge neutral dg-legend-badge", badgeEntry, "+3");
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
      centerCardId: null,
      openDetails: new Set(),
      multipleDetails: false,
      cards: new Map(),
      view: {x: 0, y: 0, scale: 1},
      autoFit: true,
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
    fitView(state);
    const controller = {
      select: (nodeId) => selectNode(state, nodeId, false),
      expandAll: () => setAllExpanded(state, true),
      collapseAll: () => setAllExpanded(state, false),
      fit: () => fitView(state),
      destroy: () => {
        state.exitFullScreen();
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

  return {render, scoreColor, layout, initialExpanded, truncateLabel, labelLines, nodeBounds, treeRoute, causeRoute, causeRouteClear, routingObstacles, roundedPath, LAYOUT, DETAIL_WIDTH, MOTION_MS};
});
