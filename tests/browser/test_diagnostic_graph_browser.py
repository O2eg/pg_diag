from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pg_diag import runtime_config
from pg_diag.render.html import render_html


pytestmark = pytest.mark.skipif(
    os.environ.get("PG_DIAG_BROWSER_TESTS") != "1",
    reason="set PG_DIAG_BROWSER_TESTS=1 to run Playwright renderer tests",
)

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "diagnostic_graph" / "lab_snapshots.json"


def _artifact() -> dict:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for item in fixture["items"].values():
        item.setdefault("source_metadata", {"tags": []})
        item.setdefault("issues", {})
        item.setdefault("collection_scope", "once")
    sections = {
        section["section_id"]: {"title": section["title"], "items": {}}
        for section in fixture["sections"]
    }
    return {
        "artifact_schema_version": runtime_config.ARTIFACT_SCHEMA_VERSION,
        "generator": {"name": "pg_diag", "version": "test"},
        "content": {
            "schema_version": runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION,
            "content_path": "/tmp/test-content",
            "checksum": "sha256:test",
            "report_id": "diagnostic-graph-browser-test",
            "document": {
                "report": {"id": "diagnostic-graph-browser-test", "title": "Graph Browser Test"},
                "runtime_policy": {},
                "defaults": {"table": {"page_size": 25}},
                "sections": sections,
                "catalogs": {"queries": {}, "presentation": {"units": {}}},
                "queries": {},
                "scripts": {},
                "metrics": {},
                "python_sources": {},
                "sampler_providers": {},
                "fallback_items": {},
                "field_reference": {},
            },
            "provenance": {"report": ["report.yaml"], "sections": ["report.yaml"]},
        },
        "report": {"id": "diagnostic-graph-browser-test", "title": "Graph Browser Test"},
        "runtime": fixture["runtime"],
        "display": {"table": {"page_size": 25}},
        "sections": fixture["sections"],
        "items": fixture["items"],
        "query_texts": {},
        "snapshot_schemas": {},
        "snapshots": [],
        "diagnostics": [],
    }


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("viewport_width", [1600, 1920])
def test_diagnostic_graph_renders_and_navigates(
    tmp_path: Path, theme: str, viewport_width: int
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    report_path = tmp_path / "report.html"
    report_path.write_text(render_html(_artifact(), validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": viewport_width, "height": 1000})
        page.set_default_timeout(5000)
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report_path.as_uri(), wait_until="load")
        page.wait_for_selector("#diagnosticGraph .dg-node")
        page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)

        def settle() -> None:
            page.wait_for_selector('#diagnosticGraph .dg-svg[data-animating="false"]')

        styles = page.evaluate(
            """() => {
              const graph = document.querySelector('#diagnosticGraph');
              const style = getComputedStyle(graph);
              return {
                sheetPresent: !!document.querySelector('head > style#pg-diag-graph-css'),
                edgeVariable: style.getPropertyValue('--dg-edge').trim(),
                nodataVariable: style.getPropertyValue('--dg-nodata').trim(),
                edgeStroke: getComputedStyle(graph.querySelector('.dg-edge')).stroke,
                nodataFill: getComputedStyle(graph.querySelector('.dg-legend .dg-dot-no_data')).backgroundColor,
              };
            }"""
        )
        assert styles["sheetPresent"]
        assert styles["edgeVariable"] and styles["nodataVariable"]
        for field in ("edgeStroke", "nodataFill"):
            assert styles[field] not in {"none", "transparent", "rgba(0, 0, 0, 0)"}, field

        state = page.evaluate(
            """() => {
              const evaluation = window.pgDiagReport.diagnosticGraph;
              return {
                roots: evaluation.roots,
                nodes: document.querySelectorAll("#diagnosticGraph .dg-node").length,
                rootStatuses: evaluation.roots.map((id) => evaluation.nodes[id].status),
                errors: evaluation.order.filter((id) => evaluation.nodes[id].error).length,
                width: document.querySelector("#diagnosticGraph svg").getBoundingClientRect().width,
              };
            }"""
        )
        assert state["roots"] == ["cpu", "ram", "disk", "database_health", "database_security"]
        assert state["nodes"] >= 5
        assert state["errors"] == 0
        assert "no_data" not in state["rootStatuses"]
        assert state["width"] <= viewport_width, "the canvas must not widen the report"
        assert page.locator("#diagnosticGraph .dg-score").count() == 0
        assert page.locator("#diagnosticGraph .dg-link").count() == 0
        assert "Bottleneck" not in page.inner_text("#diagnosticGraph")
        assert page.locator("#diagnosticGraph svg text").evaluate_all(
            "labels => labels.every(label => !label.textContent.includes('%'))"
        )
        assert page.locator("#diagnosticGraph .dg-node-root").evaluate_all(
            """nodes => nodes.every(node => {
              const box = node.querySelector('.dg-label').getBBox();
              const radius = +node.querySelector('circle').getAttribute('r');
              return [box.x, box.x + box.width].every(x =>
                [box.y, box.y + box.height].every(y => Math.hypot(x, y) < radius));
            })"""
        )

        scene = page.locator("#diagnosticGraph .dg-scene")

        def transform() -> dict:
            return scene.evaluate(
                "s => { const m = s.transform.baseVal.consolidate().matrix; return {scale: m.a, x: m.e, y: m.f}; }"
            )

        assert transform()["scale"] >= 0.7, "initial labels must stay readable"
        page.get_by_role("button", name="Fit graph", exact=True).click()
        fit = transform()
        page.get_by_role("button", name="Zoom in", exact=True).click()
        zoomed = transform()
        assert zoomed["scale"] > fit["scale"]
        page.get_by_role("button", name="Zoom out", exact=True).click()
        assert transform()["scale"] == pytest.approx(fit["scale"], rel=1e-5)

        svg = page.locator("#diagnosticGraph .dg-svg")
        svg.scroll_into_view_if_needed()
        rect = svg.bounding_box()
        assert rect is not None
        start = transform()
        x, y = rect["x"] + 100, rect["y"] + rect["height"] - 70
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 80, y - 50, steps=8)
        page.mouse.up()
        assert transform()["x"] == pytest.approx(start["x"] + 80, abs=1)
        assert transform()["y"] == pytest.approx(start["y"] - 50, abs=1)
        assert page.locator("#diagnosticGraph .dg-node-selected").count() == 0
        page.mouse.wheel(0, -150)
        page.wait_for_function(
            "scale => document.querySelector('#diagnosticGraph .dg-scene').transform.baseVal.consolidate().matrix.a > scale",
            arg=start["scale"],
        )
        page.get_by_role("button", name="Fit graph", exact=True).click()
        assert transform()["scale"] == pytest.approx(fit["scale"], rel=1e-5)

        # All causes are reachable, but only links of the selection are drawn.
        page.locator("#diagnosticGraph").get_by_role(
            "button", name="Expand all", exact=True
        ).click()
        settle()
        page.click('#diagnosticGraph .dg-node[data-node-id="ram.work_mem"]')
        settle()
        links = page.locator("#diagnosticGraph .dg-link")
        assert links.count() > 0
        assert links.evaluate_all(
            """links => links.every(link =>
              [link.dataset.from, link.dataset.to].includes('ram.work_mem') &&
              getComputedStyle(link).stroke !== 'none')"""
        )

        # Dragging a node must not trigger selection or collapse its children.
        page.get_by_role("button", name="Fit graph", exact=True).click()
        node = page.locator('#diagnosticGraph .dg-node[data-node-id="cpu"]')
        box = node.bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(
            box["x"] + box["width"] / 2 + 60, box["y"] + box["height"] / 2 + 30, steps=8
        )
        page.mouse.up()
        assert (
            page.locator("#diagnosticGraph .dg-node-selected").get_attribute("data-node-id")
            == "ram.work_mem"
        )
        assert node.get_attribute("data-children-expanded") == "true"
        page.get_by_role("button", name="Fit graph", exact=True).click()

        # Keyboard navigation survives redraws; hide/show keeps the viewport.
        node.focus()
        node.press("Enter")
        settle()
        assert page.evaluate("document.activeElement.dataset.nodeId") == "cpu"
        before_key = transform()
        node.press("ArrowRight")
        assert transform()["x"] == pytest.approx(before_key["x"] - 50, abs=1)
        header = page.locator("#diagnosticGraph .dg-header")
        saved_view = transform()
        header.get_by_role("button", name="Hide", exact=True).click()
        assert not svg.is_visible()
        header.get_by_role("button", name="Show", exact=True).click()
        assert svg.is_visible()
        assert transform() == saved_view
        page.get_by_role("button", name="Fit graph", exact=True).click()

        page.click('#diagnosticGraph .dg-node[data-node-id="database_security"]')
        settle()
        assert "%" not in page.inner_text("#diagnosticGraph .dg-panel-head")
        assert "%" not in page.inner_text("#diagnosticGraph .dg-children")
        page.click('#diagnosticGraph .dg-node[data-node-id="security.authentication"]')
        settle()
        panel_text = page.inner_text("#diagnosticGraph .dg-panel")
        assert "security.authentication" in panel_text
        assert "report items" in panel_text.lower()
        assert "Bottleneck" not in panel_text

        layout = page.evaluate(
            """() => {
              const graph = document.querySelector('#diagnosticGraph');
              const node = graph.querySelector('.dg-node-selected').getBoundingClientRect();
              const panel = graph.querySelector('.dg-panel').getBoundingClientRect();
              const detail = graph.querySelector('.dg-detail');
              return {
                nodeBottom: node.bottom,
                nodeCenter: node.x + node.width / 2,
                panelTop: panel.top,
                panelCenter: panel.x + panel.width / 2,
                panelWidth: panel.width,
                inline: !!detail.closest('.dg-scene'),
                scale: graph.querySelector('.dg-scene').transform.baseVal.consolidate().matrix.a,
                panelBackground: getComputedStyle(graph.querySelector('.dg-panel')).backgroundColor,
                bindings: window.pgDiagReport.diagnosticGraph.nodes['security.authentication'].bindings.length,
                chips: graph.querySelectorAll('.dg-panel .dg-item').length,
              };
            }"""
        )
        assert layout["inline"]
        assert layout["panelTop"] > layout["nodeBottom"]
        assert layout["panelCenter"] == pytest.approx(layout["nodeCenter"], abs=1)
        assert layout["panelWidth"] == pytest.approx(520 * layout["scale"], abs=1)
        assert layout["chips"] == layout["bindings"]
        assert layout["panelBackground"] not in {"transparent", "rgba(0, 0, 0, 0)"}
        assert page.locator("#diagnosticGraph .dg-body > .dg-panel").count() == 0

        page.get_by_role("button", name="Fit graph", exact=True).click()
        chip = page.locator("#diagnosticGraph .dg-item:not([disabled])").first
        item_id = chip.get_attribute("data-item-id")
        chip.click()
        page.wait_for_function(
            '([itemId]) => document.querySelector(`details.item[data-item-id="${itemId}"]`).open',
            arg=[item_id],
        )
        scrolled = page.evaluate("window.scrollY")
        assert scrolled > 0, "clicking an item chip scrolls the report to the item"
        assert errors == []
        browser.close()


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("reduced_motion", ["no-preference", "reduce"])
def test_inline_details_animate_and_handle_interruption(
    tmp_path: Path, theme: str, reduced_motion: str
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    report_path = tmp_path / "report.html"
    report_path.write_text(render_html(_artifact(), validate=False), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1600, "height": 1000}, reduced_motion=reduced_motion
        )
        page.set_default_timeout(5000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report_path.as_uri(), wait_until="load")
        page.wait_for_selector("#diagnosticGraph .dg-node")
        page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)

        samples = page.evaluate(
            """async () => {
              const graph = document.querySelector('#diagnosticGraph');
              const sample = () => {
                const peer = graph.querySelector('.dg-node[data-node-id="ram.pressure"]');
                const selected = graph.querySelector('.dg-node[data-node-id="cpu"]');
                const box = selected.querySelector('circle').getBoundingClientRect();
                const card = graph.querySelector('.dg-detail');
                return {
                  peerY: peer.transform.baseVal.consolidate().matrix.f,
                  selectedX: box.x + box.width / 2,
                  selectedY: box.y + box.height / 2,
                  height: card ? +card.getAttribute('height') : 0,
                  scale: graph.querySelector('.dg-scene').transform.baseVal.consolidate().matrix.a,
                };
              };
              const settled = async () => {
                while (graph.querySelector('.dg-svg').dataset.animating === 'true')
                  await new Promise(requestAnimationFrame);
              };
              const node = () => graph.querySelector('.dg-node[data-node-id="cpu"]');
              const before = sample();
              node().dispatchEvent(new MouseEvent('click', {bubbles: true}));
              const opening = graph.querySelector('.dg-svg').dataset.animating;
              await new Promise(resolve => setTimeout(resolve, 90));
              const middle = sample();
              await settled();
              const open = sample();
              node().dispatchEvent(new MouseEvent('click', {bubbles: true}));
              await new Promise(resolve => setTimeout(resolve, 90));
              const closing = sample();
              await settled();
              const closed = sample();
              return {before, opening, middle, open, closing, closed};
            }"""
        )
        assert samples["open"]["height"] > 100
        assert samples["open"]["peerY"] > samples["before"]["peerY"]
        assert samples["closed"]["height"] == 0
        assert samples["closed"]["peerY"] == pytest.approx(samples["before"]["peerY"])
        for phase in ["middle", "open", "closing", "closed"]:
            assert samples[phase]["scale"] == samples["before"]["scale"]
            assert samples[phase]["selectedX"] == pytest.approx(
                samples["before"]["selectedX"], abs=1
            )
            assert samples[phase]["selectedY"] == pytest.approx(
                samples["before"]["selectedY"], abs=1
            )
        if reduced_motion == "no-preference":
            assert samples["opening"] == "true"
            assert 0 < samples["middle"]["height"] < samples["open"]["height"]
            assert 0 < samples["closing"]["height"] < samples["open"]["height"]
            assert (
                samples["before"]["peerY"] < samples["middle"]["peerY"] < samples["open"]["peerY"]
            )
        else:
            assert samples["opening"] == "false"

        # Interrupt opening, closing and a switch to a different node.
        page.evaluate(
            """async () => {
              const click = id => document.querySelector(`.dg-node[data-node-id="${id}"]`)
                .dispatchEvent(new MouseEvent('click', {bubbles: true}));
              click('cpu');
              await new Promise(resolve => setTimeout(resolve, 35));
              click('cpu');
              await new Promise(resolve => setTimeout(resolve, 35));
              click('cpu');
              await new Promise(resolve => setTimeout(resolve, 35));
              click('ram');
            }"""
        )
        page.wait_for_selector('#diagnosticGraph .dg-svg[data-animating="false"]')
        assert page.locator("#diagnosticGraph .dg-detail").count() == 1
        assert page.locator("#diagnosticGraph .dg-detail").get_attribute("data-node-id") == "ram"
        assert page.locator("#diagnosticGraph .dg-panel").evaluate(
            "p => !p.inert && p.scrollHeight <= p.offsetHeight + 1"
        )
        # A card is truly in scene coordinates, not an unscaled DOM overlay.
        size_before = page.locator("#diagnosticGraph .dg-panel").bounding_box()
        page.get_by_role("button", name="Zoom in", exact=True).click()
        size_after = page.locator("#diagnosticGraph .dg-panel").bounding_box()
        assert size_before and size_after
        assert size_after["width"] == pytest.approx(size_before["width"] * 1.4, abs=1)
        assert size_after["height"] == pytest.approx(size_before["height"] * 1.4, abs=1)

        # Re-render during motion must retire the old animation and observers.
        page.evaluate(
            """() => {
              const container = document.querySelector('#diagnosticGraph');
              container.querySelector('.dg-node[data-node-id="cpu"]').dispatchEvent(new MouseEvent('click', {bubbles: true}));
              window.PgDiagGraphRender.render(container, window.pgDiagReport.diagnosticGraph, {collapsed: false});
            }"""
        )
        page.wait_for_timeout(350)
        assert page.locator("#diagnosticGraph .dg-detail").count() == 0
        assert page.locator("#diagnosticGraph .dg-measurer").count() == 1
        assert errors == []
        browser.close()
