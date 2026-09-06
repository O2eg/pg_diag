/* Read the rendered SVG, including the rounded curves and arrow endpoints. */
async function inspectArrowScaling() {
  const link = document.querySelector('#diagnosticGraph .dg-link[data-kind="cause"]');
  if (!link) throw new Error('Select a node with a visible cause link before checking arrow scaling');
  const marker = link.ownerSVGElement.querySelector('#dg-arrow');
  const style = getComputedStyle(link);
  const svgNS = 'http://www.w3.org/2000/svg';
  const samples = [];
  for (const scale of [0.25, 0.5, 1, 2]) {
    // Rasterize the actual marker and link styles on a short isolated segment.
    // DOM bounds of <marker> describe its definition, not the painted instance.
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('width', '160'); svg.setAttribute('height', '160');
    const defs = document.createElementNS(svgNS, 'defs'), copy = marker.cloneNode(true);
    copy.id = 'audit-arrow'; copy.querySelector('path').setAttribute('fill', '#ff00ff');
    defs.appendChild(copy); svg.appendChild(defs);
    const group = document.createElementNS(svgNS, 'g');
    group.setAttribute('transform', `translate(80,40) scale(${scale})`);
    const path = document.createElementNS(svgNS, 'path');
    path.setAttribute('d', 'M0,0 V40'); path.setAttribute('marker-end', 'url(#audit-arrow)');
    path.setAttribute('fill', 'none'); path.setAttribute('stroke', '#000');
    path.setAttribute('stroke-width', style.strokeWidth);
    path.setAttribute('stroke-dasharray', style.strokeDasharray);
    path.setAttribute('vector-effect', style.vectorEffect);
    group.appendChild(path); svg.appendChild(group);
    const image = new Image();
    image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(svg));
    await image.decode();
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 160;
    const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, 160, 160).data;
    let left = 160, top = 160, right = -1, bottom = -1;
    for (let y = 0; y < 160; y++) for (let x = 0; x < 160; x++) {
      const i = (y * 160 + x) * 4;
      if (pixels[i] > 180 && pixels[i + 1] < 80 && pixels[i + 2] > 180 && pixels[i + 3] > 64) {
        left = Math.min(left, x); right = Math.max(right, x);
        top = Math.min(top, y); bottom = Math.max(bottom, y);
      }
    }
    // Measure the line separately so the head cannot cover its narrow stroke.
    path.removeAttribute('marker-end');
    image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(svg));
    await image.decode();
    context.clearRect(0, 0, 160, 160); context.drawImage(image, 0, 0);
    const linePixels = context.getImageData(0, 0, 160, 160).data;
    let strokeWidth = 0;
    for (let y = 0; y < 160; y++) {
      let coverage = 0;
      for (let x = 0; x < 160; x++) coverage += linePixels[(y * 160 + x) * 4 + 3] / 255;
      strokeWidth = Math.max(strokeWidth, coverage);
    }
    samples.push({scale, width: Math.max(0, right - left + 1), height: Math.max(0, bottom - top + 1), strokeWidth});
  }
  const baseline = samples.find(sample => sample.scale === 1);
  const problems = samples.filter(sample => !sample.width || !sample.height
    || Math.abs(sample.width - baseline.width * sample.scale) > 1
    || Math.abs(sample.height - baseline.height * sample.scale) > 1
    || Math.abs(sample.strokeWidth - baseline.strokeWidth * sample.scale) > 0.15);
  return {samples, problems};
}

function inspectGraphLinks(options = {}) {
  const graph = document.querySelector("#diagnosticGraph"), ev = pgDiagReport.diagnosticGraph;
  const nodes = new Map(Array.from(graph.querySelectorAll(".dg-node"), element => {
    const circle = element.querySelector(".dg-circle"), m = element.transform.baseVal.consolidate().matrix;
    return [element.dataset.nodeId, {x: m.e, y: m.f, r: +circle.getAttribute("r"), opacity: +getComputedStyle(element).opacity}];
  }));
  const selected = graph.querySelector(".dg-node-selected")?.dataset.nodeId;
  const expected = ev.links.filter(link => nodes.has(link.from) && nodes.has(link.to) && [link.from, link.to].includes(selected));
  const paths = Array.from(graph.querySelectorAll(".dg-link"));
  const problems = [];
  if (paths.length !== expected.length) problems.push({kind: "link-count", expected: expected.length, actual: paths.length});
  const treePaths = options.edges ? Array.from(graph.querySelectorAll('.dg-edge[data-from]')) : [];
  const treeExpected = options.edges ? [...nodes.keys()].filter(id => nodes.has(ev.nodes[id].parent)) : [];
  if (treePaths.length !== treeExpected.length) problems.push({kind: 'edge-count', expected: treeExpected.length, actual: treePaths.length});
  const cards = Array.from(graph.querySelectorAll(".dg-detail"), element => {
    const clip = element.firstElementChild.style.clipPath.match(/inset\(\s*0(?:px)?\s+([\d.]+)px/);
    const inset = clip ? +clip[1] : 0;
    return {id: element.dataset.nodeId, x: +element.getAttribute("x") + inset,
      y: +element.getAttribute("y"), w: +element.getAttribute("width") - inset * 2,
      h: +element.getAttribute("height"), opacity: +getComputedStyle(element).opacity};
  });
  for (const element of [...paths, ...treePaths]) {
    const link = {from: element.dataset.from, to: element.dataset.to};
    const treeEdge = element.classList.contains('dg-edge');
    if (treeEdge ? ev.nodes[link.to].parent !== link.from : !expected.some(candidate => candidate.from === link.from && candidate.to === link.to)) problems.push({...link, kind: "unexpected-link"});
    const kind = expected.find(candidate => candidate.from === link.from && candidate.to === link.to)?.kind || 'cause';
    const marker = element.getAttribute('marker-end');
    if (treeEdge ? Boolean(marker) : (kind === 'related') === Boolean(marker)) problems.push({...link, kind: 'arrow-kind'});
    const d = element.getAttribute("d"), style = getComputedStyle(element);
    if (!d || /NaN|undefined|Infinity/.test(d)) {problems.push({...link, kind: "invalid-path"}); continue;}
    if (style.stroke === "none" || (treeEdge ? style.strokeDasharray !== 'none' : style.strokeDasharray === 'none')) problems.push({...link, kind: "line-style"});
    if (+style.opacity < 0.05) {
      if (graph.querySelector('.dg-svg').dataset.animating === 'false') problems.push({...link, kind: 'hidden-settled-link'});
      continue;
    }
    const length = element.getTotalLength();
    const start = element.getPointAtLength(0), end = element.getPointAtLength(length);
    const from = nodes.get(link.from), to = nodes.get(link.to);
    const sourceCard = treeEdge && cards.find(card => card.id === link.from && card.h > 0);
    const startError = sourceCard ? Math.hypot(start.x - from.x, start.y - sourceCard.y - sourceCard.h)
      : Math.abs(Math.hypot(start.x - from.x, start.y - from.y) - from.r);
    if (startError > 1) problems.push({...link, kind: "start-port"});
    if (Math.abs(Math.hypot(end.x - to.x, end.y - to.y) - to.r - (treeEdge ? 0 : 6)) > 1) problems.push({...link, kind: "end-port"});
    const crossed = new Set();
    for (let distance = 3; distance < length; distance += 6) {
      const p = element.getPointAtLength(distance);
      for (const [id, node] of nodes) {
        if (node.opacity > 0.95 && Math.hypot(p.x - node.x, p.y - node.y) < node.r - 2) crossed.add("node:" + id);
      }
      for (const card of cards) {
        if (card.opacity > 0.05 && card.h > 1 && p.x > card.x + 1 && p.x < card.x + card.w - 1 && p.y > card.y + 1 && p.y < card.y + card.h - 1) crossed.add("card:" + card.id);
      }
    }
    for (const obstacle of crossed) problems.push({...link, kind: "intersection", obstacle});
  }
  return {selected, links: paths.length, edges: treePaths.length, problems};
}
