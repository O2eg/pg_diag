/* Read the rendered SVG, including the rounded curves and arrow endpoints. */
function inspectGraphLinks() {
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
  const cards = Array.from(graph.querySelectorAll(".dg-detail"), element => {
    const clip = element.firstElementChild.style.clipPath.match(/inset\(\s*0(?:px)?\s+([\d.]+)px/);
    const inset = clip ? +clip[1] : 0;
    return {id: element.dataset.nodeId, x: +element.getAttribute("x") + inset,
      y: +element.getAttribute("y"), w: +element.getAttribute("width") - inset * 2,
      h: +element.getAttribute("height"), opacity: +getComputedStyle(element).opacity};
  });
  for (const element of paths) {
    const link = {from: element.dataset.from, to: element.dataset.to};
    if (!expected.some(candidate => candidate.from === link.from && candidate.to === link.to)) problems.push({...link, kind: "unexpected-link"});
    const kind = expected.find(candidate => candidate.from === link.from && candidate.to === link.to)?.kind || 'cause';
    const marker = element.getAttribute('marker-end');
    if ((kind === 'related') === Boolean(marker)) problems.push({...link, kind: 'arrow-kind'});
    const d = element.getAttribute("d"), style = getComputedStyle(element);
    if (!d || /NaN|undefined|Infinity/.test(d)) {problems.push({...link, kind: "invalid-path"}); continue;}
    if (style.stroke === "none" || style.strokeDasharray === "none") problems.push({...link, kind: "invisible-or-solid"});
    if (+style.opacity < 0.05) {
      if (graph.querySelector('.dg-svg').dataset.animating === 'false') problems.push({...link, kind: 'hidden-settled-link'});
      continue;
    }
    const length = element.getTotalLength();
    const start = element.getPointAtLength(0), end = element.getPointAtLength(length);
    const from = nodes.get(link.from), to = nodes.get(link.to);
    if (Math.abs(Math.hypot(start.x - from.x, start.y - from.y) - from.r) > 1) problems.push({...link, kind: "start-port"});
    if (Math.abs(Math.hypot(end.x - to.x, end.y - to.y) - to.r - 6) > 1) problems.push({...link, kind: "end-port"});
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
  return {selected, links: paths.length, problems};
}
