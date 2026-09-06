/* Read the rendered SVG, including the rounded curves and arrow endpoints. */
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
