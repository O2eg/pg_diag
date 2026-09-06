"""Native card-to-card navigation checks shared by report audits and browser tests."""

import json
import math


def check_node_links(page, node_ids=None, *, motion="no-preference"):
    """Follow cross-links in both directions, keeping zoom and centring the target card."""
    links = page.evaluate("pgDiagReport.diagnosticGraph.links")
    directions = [(link[a], link[b]) for link in links for a, b in [("from", "to"), ("to", "from")]]
    if node_ids is not None:
        assert set(node_ids) <= {source for source, _ in directions}, "Unknown node or no cross-links"
        directions = [(source, target) for source, target in directions if source in node_ids]
    graph = page.locator("#diagnosticGraph")
    results = []
    for source, target in directions:
        for expanded, scale in [(False, 1.64), (True, 0.5)]:
            # Only prepare the starting card through the API. The transition
            # under test uses a native click on the actual link in its card.
            page.emulate_media(reduced_motion="reduce")
            page.evaluate("""expanded => {
              window.auditController = PgDiagGraphRender.render(document.getElementById('diagnosticGraph'),
                pgDiagReport.diagnosticGraph, {collapsed: false});
              if (expanded) auditController.expandAll();
            }""", expanded)
            graph.get_by_role("button", name="Actual size", exact=True).click()
            svg = graph.locator(".dg-svg")
            svg.hover(position={"x": 10, "y": 100})
            page.mouse.wheel(0, -math.log(scale) / 0.002)
            page.wait_for_function("scale => Math.abs(auditController.state.view.scale - scale) < 0.001", arg=scale)
            page.evaluate("id => auditController.select(id)", source)
            target_label = page.evaluate("id => pgDiagReport.diagnosticGraph.nodes[id].label", target)
            link = graph.locator('.dg-detail[data-node-id=' + json.dumps(source) + '] .dg-causes').get_by_role(
                "button", name=target_label, exact=True
            )
            # Large cards can exceed the viewport. Pan with the existing
            # keyboard controls until the link is on screen, preserving zoom.
            offset = link.evaluate("""button => {
              const box = button.getBoundingClientRect();
              const svg = document.querySelector('#diagnosticGraph .dg-svg');
              const canvas = svg.getBoundingClientRect();
              svg.focus({preventScroll: true});
              return canvas.y + canvas.height / 2 - box.y - box.height / 2;
            }""")
            for _ in range(round(abs(offset) / 50)):
                page.keyboard.press("ArrowUp" if offset > 0 else "ArrowDown")
            page.emulate_media(reduced_motion=motion)
            # Capture immediately after the handler, before the first RAF.
            link.evaluate("""button => {
              const view = () => ({...auditController.state.view});
              window.auditLinkStart = {before: view()};
              button.addEventListener('click', () => queueMicrotask(() => {
                auditLinkStart.after = view();
              }), {once: true});
            }""")
            link.click(timeout=5000)
            page.wait_for_selector('#diagnosticGraph .dg-svg[data-animating="false"]')
            entry = page.evaluate("""target => {
              const svg = document.querySelector('#diagnosticGraph .dg-svg');
              const canvas = svg.getBoundingClientRect();
              const panel = svg.querySelector(`.dg-detail[data-node-id="${target}"] .dg-panel`);
              const box = panel.getBoundingClientRect();
              return {selected: auditController.state.selected, scale: auditController.state.view.scale,
                dx: box.x + box.width / 2 - canvas.x - canvas.width / 2,
                dy: box.y + box.height / 2 - canvas.y - canvas.height / 2,
                jump: Math.hypot(auditLinkStart.after.x - auditLinkStart.before.x,
                  auditLinkStart.after.y - auditLinkStart.before.y),
                cards: svg.querySelectorAll('.dg-detail').length};
            }""", target)
            problems = []
            if entry["selected"] != target or entry["cards"] != 1:
                problems.append("wrong-target-card")
            if abs(entry["dx"]) > 1 or abs(entry["dy"]) > 1:
                problems.append("card-not-centred")
            if abs(entry["scale"] - scale) > 0.001:
                problems.append("zoom-changed")
            if motion == "no-preference" and entry["jump"] > 1:
                problems.append("instant-pan-before-animation")
            results.append({"from": source, "to": target, "expanded": expanded,
                            "motion": motion, **entry, "problems": problems})
    return results
