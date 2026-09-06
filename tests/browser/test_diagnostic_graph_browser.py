from __future__ import annotations

import json
import os
import runpy
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
@pytest.mark.parametrize("reduced_motion", ["no-preference", "reduce"])
def test_card_links_centre_target_without_jumping(tmp_path: Path, theme: str, reduced_motion: str) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    helpers = Path(__file__).resolve().parents[2] / "tools/report_debug/browser_interactions.py"
    check_links = runpy.run_path(str(helpers))["check_node_links"]
    report_path = tmp_path / "report.html"
    report_path.write_text(render_html(_artifact(), validate=False), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report_path.as_uri(), wait_until="load")
        page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
        # Related checks, causes, and their reverse links, including a hidden
        # destination in another root and a card taller than the viewport.
        entries = check_links(
            page, ["cpu.session_churn", "health.connections", "disk.space", "health.replication"],
            motion=reduced_motion,
        )
        assert entries
        assert not [entry for entry in entries if entry["problems"]]
        assert not errors
        browser.close()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_cause_arrow_and_dashed_stroke_scale_with_canvas(tmp_path: Path, theme: str) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    report_path = tmp_path / "report.html"
    report_path.write_text(render_html(_artifact(), validate=False), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, reduced_motion="reduce")
        page.goto(report_path.as_uri(), wait_until="load")
        page.evaluate("""theme => {
          document.documentElement.dataset.theme = theme;
          const controller = PgDiagGraphRender.render(document.getElementById('diagnosticGraph'),
            pgDiagReport.diagnosticGraph, {collapsed: false});
          controller.expandAll();
          controller.select(pgDiagReport.diagnosticGraph.links.find(link => link.kind !== 'related').from);
        }""", theme)
        page.add_script_tag(path=str(Path(__file__).resolve().parents[2] / "tools/report_debug/browser_routes.js"))
        result = page.evaluate("inspectArrowScaling()")
        assert len(result["samples"]) == 4
        assert not result["problems"], result
        browser.close()


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
                nodataFill: getComputedStyle(graph.querySelector('.dg-legend .dg-dot-no_data')).backgroundColor,
              };
            }"""
        )
        assert styles["sheetPresent"]
        assert styles["edgeVariable"] and styles["nodataVariable"]
        for field in ("nodataFill",):
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
        assert state["roots"] == ["cpu", "ram", "disk", "network", "database_health", "database_security"]
        assert state["nodes"] == 6
        assert page.locator("#diagnosticGraph .dg-edge").count() == 0
        assert page.locator("#diagnosticGraph .dg-node-root .dg-label").evaluate_all(
            "labels => labels.length === 6 && labels.every(label => getComputedStyle(label).fontSize === '42px')"
        )
        assert page.locator("#diagnosticGraph .dg-header").get_by_role(
            "button", name="Expand all", exact=True
        ).count() == 0
        assert state["errors"] == 0
        assert "no_data" not in state["rootStatuses"]
        assert state["width"] <= viewport_width, "the canvas must not widen the report"
        assert page.locator("#diagnosticGraph .dg-score").count() == 0
        assert page.locator("#diagnosticGraph .dg-link").count() == 0
        assert "Bottleneck" not in page.inner_text("#diagnosticGraph")
        assert page.locator("#diagnosticGraph svg text").evaluate_all(
            "labels => labels.every(label => !label.textContent.includes('%'))"
        )
        def assert_labels_inside_circles() -> None:
            assert page.locator("#diagnosticGraph .dg-node").evaluate_all(
                """nodes => nodes.every(node => {
                  const box = node.querySelector('.dg-label').getBoundingClientRect();
                  const circle = node.querySelector('.dg-circle').getBoundingClientRect();
                  const cx = circle.x + circle.width / 2, cy = circle.y + circle.height / 2;
                  const inside = b => circle.width > 0 && [b.left, b.right].every(x =>
                    [b.top, b.bottom].every(y => Math.hypot(x - cx, y - cy) < circle.width / 2));
                  const badge = node.querySelector('.dg-badge');
                  const lines = [...node.querySelectorAll('.dg-label tspan')].map(line => +line.getAttribute('y'));
                  const fontSize = parseFloat(getComputedStyle(node.querySelector('.dg-label')).fontSize);
                  if (lines.some((y, i) => i > 0 && y - lines[i - 1] < fontSize)) return false;
                  if (!badge) return inside(box);
                  const pill = badge.getBoundingClientRect();
                  const style = getComputedStyle(badge), labelStyle = getComputedStyle(node.querySelector('.dg-label'));
                  const reference = getComputedStyle(document.querySelector('.badge.neutral:not(.dg-badge)'));
                  return inside(box) && inside(pill) && pill.top > box.bottom &&
                    style.fontSize === labelStyle.fontSize &&
                    ['backgroundColor', 'color', 'borderRadius'].every(key => style[key] === reference[key]);
                })"""
            )

        assert_labels_inside_circles()
        assert page.locator("#diagnosticGraph .dg-node-badge").count() > 0

        scene = page.locator("#diagnosticGraph .dg-scene")

        def transform() -> dict:
            return scene.evaluate(
                "s => { const m = s.transform.baseVal.consolidate().matrix; return {scale: m.a, x: m.e, y: m.f}; }"
            )

        initial_view = transform()
        page.get_by_role("button", name="Fit graph", exact=True).click()
        fit = transform()
        assert initial_view == pytest.approx(fit), "initial view must match the Fit button"
        page.get_by_role("button", name="Zoom in", exact=True).click()
        zoomed = transform()
        assert zoomed["scale"] > fit["scale"]
        page.get_by_role("button", name="Zoom out", exact=True).click()
        assert transform()["scale"] == pytest.approx(fit["scale"], rel=1e-5)

        # Full screen fills the page and reuses Fit; both exit paths restore it.
        graph = page.locator("#diagnosticGraph")
        graph.get_by_role("button", name="Fit graph", exact=True).click()
        graph.get_by_role("button", name="Full screen", exact=True).click()
        fullscreen = graph.locator(".dg-fullscreen")
        assert fullscreen.evaluate("d => d.open && d.matches(':modal')")
        for name in ("Expand all", "Collapse all"):
            assert fullscreen.locator(".dg-zoom").get_by_role("button", name=name, exact=True).is_visible()
        assert graph.locator(".dg-svg").bounding_box() == pytest.approx(
            {"x": 0, "y": 0, "width": viewport_width, "height": 1000}
        )
        page.wait_for_function(
            "scale => document.querySelector('#diagnosticGraph .dg-scene').transform.baseVal.consolidate().matrix.a > scale",
            arg=fit["scale"],
        )
        fullscreen_fit = transform()
        graph.get_by_role("button", name="Fit graph", exact=True).click()
        assert transform() == pytest.approx(fullscreen_fit)
        page.keyboard.press("Escape")
        assert not fullscreen.evaluate("d => d.open")
        assert transform() == pytest.approx(fit)

        graph.get_by_role("button", name="Zoom in", exact=True).click()
        manual_view = transform()
        graph.get_by_role("button", name="Full screen", exact=True).click()
        assert transform()["scale"] == pytest.approx(manual_view["scale"])
        graph.get_by_role("button", name="Exit full screen", exact=True).click()
        assert transform() == pytest.approx(manual_view)
        assert page.evaluate("document.documentElement.style.overflow") == ""
        graph.get_by_role("button", name="Fit graph", exact=True).click()

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
        assert_labels_inside_circles()
        assert page.locator("#diagnosticGraph .dg-node-badge").count() == 0
        assert page.locator("#diagnosticGraph .dg-edge").first.evaluate(
            "edge => !['none', 'transparent', 'rgba(0, 0, 0, 0)'].includes(getComputedStyle(edge).stroke)"
        )
        expanded_count = page.locator("#diagnosticGraph .dg-node").count()
        assert expanded_count == page.evaluate("pgDiagReport.diagnosticGraph.order.length")
        assert graph.locator('.dg-detail').count() <= 1, 'first step reveals the tree'
        graph.locator(".dg-zoom").get_by_role("button", name="Expand all", exact=True).click()
        settle()
        assert page.locator("#diagnosticGraph .dg-node").count() == expanded_count
        assert graph.locator('.dg-detail').count() == expanded_count
        assert graph.locator('.dg-node[aria-expanded="true"]').count() == expanded_count
        assert graph.locator('.dg-detail .dg-panel').evaluate_all('cards => cards.every(card => !card.inert)')
        assert graph.get_by_role('button', name='Expand all', exact=True).is_disabled()
        assert graph.locator('.dg-detail').evaluate_all("""cards => {
          const canvas = document.querySelector('#diagnosticGraph .dg-svg').getBoundingClientRect();
          return cards.every(card => {
            const box = card.getBoundingClientRect();
            return box.left >= canvas.left && box.right <= canvas.right && box.top >= canvas.top && box.bottom <= canvas.bottom;
          });
        }""")
        # Closing one card keeps the expanded tree and all other cards intact.
        close_card = graph.locator('.dg-detail[data-node-id="ram.work_mem"] .dg-panel-close')
        close_card.scroll_into_view_if_needed()
        box = close_card.bounding_box()
        assert box is not None
        # Fit is an overview of hundreds of cards; zoom at the target control.
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        for _ in range(4):
            page.mouse.wheel(0, -500)
        page.wait_for_function("document.querySelector('.dg-detail[data-node-id=\"ram.work_mem\"] .dg-panel-close').getBoundingClientRect().width > 8")
        close_card.click()
        settle()
        assert graph.locator('.dg-detail').count() == expanded_count - 1
        assert graph.locator('.dg-node').count() == expanded_count
        assert graph.get_by_role('button', name='Expand all', exact=True).is_enabled()
        graph.get_by_role('button', name='Expand all', exact=True).click()
        settle()
        assert graph.locator('.dg-detail').count() == expanded_count
        graph.locator(".dg-zoom").get_by_role("button", name="Collapse all", exact=True).click()
        settle()
        assert page.locator("#diagnosticGraph .dg-node").count() == 6
        assert page.locator("#diagnosticGraph .dg-detail, #diagnosticGraph .dg-node-selected").count() == 0
        assert transform() == pytest.approx(initial_view)
        graph.locator(".dg-zoom").get_by_role("button", name="Expand all", exact=True).click()
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
        assert page.locator("#diagnosticGraph .dg-children").count() == 0
        page.click('#diagnosticGraph .dg-node[data-node-id="security.authentication"]')
        settle()
        assert page.locator("#diagnosticGraph .dg-item").count() == 0
        page.click(
            '#diagnosticGraph .dg-node[data-node-id="security.authentication.sources.hba"]'
        )
        settle()
        panel_text = page.inner_text("#diagnosticGraph .dg-panel")
        assert "security.authentication" in panel_text
        assert "report items" in panel_text.lower()
        assert "Bottleneck" not in panel_text
        assert "Data available" not in panel_text
        assert page.locator("#diagnosticGraph .dg-children").count() == 0
        assert page.locator("#diagnosticGraph .dg-node-selected .dg-circle").evaluate(
            """circle => getComputedStyle(circle).fill ===
              getComputedStyle(document.querySelector('#diagnosticGraph .dg-status')).backgroundColor"""
        )

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
                bindings: window.pgDiagReport.diagnosticGraph.nodes['security.authentication.sources.hba'].bindings.length,
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
        graph.get_by_role("button", name="Full screen", exact=True).click()
        chip = page.locator("#diagnosticGraph .dg-item:not([disabled])").first
        item_id = chip.get_attribute("data-item-id")
        chip.click()
        assert not fullscreen.evaluate("d => d.open")
        page.wait_for_function(
            '([itemId]) => document.querySelector(`details.item[data-item-id="${itemId}"]`).open',
            arg=[item_id],
        )
        scrolled = page.evaluate("window.scrollY")
        assert scrolled > 0, "clicking an item chip scrolls the report to the item"

        # Long captions also fit when rendering starts with a hidden canvas.
        captions = {"cpu": "W" * 50, "cpu.utilization": "Ж" * 51, "cpu.system_time": "😀" * 50}
        page.evaluate(
            """captions => {
              const evaluation = window.pgDiagReport.diagnosticGraph;
              for (const [id, label] of Object.entries(captions)) evaluation.nodes[id].label = label;
              PgDiagGraphRender.render(document.querySelector('#diagnosticGraph'), evaluation, {collapsed: true});
            }""",
            captions,
        )
        graph.get_by_role("button", name="Show", exact=True).click()
        assert_labels_inside_circles()
        root = graph.locator('.dg-node[data-node-id="cpu"]')
        root.click()
        settle()
        assert_labels_inside_circles()
        for node_id, caption in captions.items():
            node = graph.locator(f'.dg-node[data-node-id="{node_id}"]')
            expected = caption if len(caption) <= 50 else caption[:49] + "…"
            assert node.locator(".dg-label").text_content() == expected
            assert caption in node.locator("title").text_content()
        root.click()
        settle()
        assert_labels_inside_circles()
        counter = root.locator(".dg-badge")
        assert counter.text_content() == "+4"
        box = counter.bounding_box()
        assert box is not None
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        settle()
        assert root.get_attribute("data-children-expanded") == "true"
        assert root.locator(".dg-badge").count() == 0
        assert errors == []
        browser.close()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_network_details_navigate_at_canvas_scale(tmp_path: Path, theme: str) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    report_path = tmp_path / "report.html"
    report_path.write_text(render_html(_artifact(), validate=False), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(5000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report_path.as_uri())
        page.wait_for_selector("#diagnosticGraph .dg-node")
        page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
        page.get_by_role("button", name="Fit graph", exact=True).click()
        page.locator('.dg-node[data-node-id="network"]').click()
        page.wait_for_selector('.dg-svg[data-animating="false"]')
        assert page.locator('.dg-detail').get_attribute('data-node-id') == "network"
        page.locator("#diagnosticGraph").get_by_role("button", name="Expand all", exact=True).click()
        page.wait_for_selector('.dg-svg[data-animating="false"]')
        page.get_by_role("button", name="Fit graph", exact=True).click()
        page.locator('.dg-node[data-node-id="network.traffic.receive"]').click()
        page.wait_for_selector('.dg-svg[data-animating="false"]')
        assert "mean / p95 / peak" in page.locator('.dg-panel').inner_text()
        assert "No matching current link speed" in page.locator('.dg-panel').inner_text()
        page.get_by_role("button", name="Fit graph", exact=True).click()
        page.locator('.dg-item[data-item-id="snapshot_charts_os.os_network_receive"]').click()
        page.wait_for_function("document.querySelector('details.item[data-item-id=\"snapshot_charts_os.os_network_receive\"]').open")
        assert not errors
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
                const peer = graph.querySelector('.dg-node[data-node-id="ram"]');
                const selected = graph.querySelector('.dg-node[data-node-id="cpu"]');
                const box = selected.querySelector('circle').getBoundingClientRect();
                const card = graph.querySelector('.dg-detail');
                const cardBox = card && card.getBoundingClientRect();
                const canvas = graph.querySelector('.dg-svg').getBoundingClientRect();
                return {
                  peerY: peer.transform.baseVal.consolidate().matrix.f,
                  healthY: graph.querySelector('.dg-node[data-node-id="database_health"]').transform.baseVal.consolidate().matrix.f,
                  securityY: graph.querySelector('.dg-node[data-node-id="database_security"]').transform.baseVal.consolidate().matrix.f,
                  selectedX: box.x + box.width / 2,
                  selectedY: box.y + box.height / 2,
                  cardX: cardBox ? cardBox.x + cardBox.width / 2 : null,
                  cardY: cardBox ? cardBox.y + cardBox.height / 2 : null,
                  canvasX: canvas.x + canvas.width / 2,
                  canvasY: canvas.y + canvas.height / 2,
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
        assert samples["closed"]["height"] == 0
        for field in ["healthY", "securityY"]:
            assert samples["open"][field] > samples["before"][field]
            assert samples["closed"][field] <= samples["before"][field]
        for phase in ["middle", "open", "closing", "closed"]:
            assert samples[phase]["peerY"] == pytest.approx(samples["before"]["peerY"])
            assert samples[phase]["scale"] == samples["before"]["scale"]
        for axis in ["X", "Y"]:
            assert samples["open"]["card" + axis] == pytest.approx(samples["open"]["canvas" + axis], abs=1)
            for phase in ["closing", "closed"]:
                assert samples[phase]["selected" + axis] == pytest.approx(samples["open"]["selected" + axis], abs=1)
        if reduced_motion == "no-preference":
            assert samples["opening"] == "true"
            assert 0 < samples["middle"]["height"] < samples["open"]["height"]
            assert 0 < samples["closing"]["height"] < samples["open"]["height"]
            for field in ["healthY", "securityY"]:
                assert samples["before"][field] < samples["middle"][field] < samples["open"][field]
            for field in ["selectedX", "selectedY"]:
                distance = abs(samples["open"][field] - samples["before"][field])
                if distance > 1:
                    assert 0 < abs(samples["middle"][field] - samples["before"][field]) < distance
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
        assert page.locator("#diagnosticGraph .dg-panel").evaluate("""panel => {
          const card = panel.getBoundingClientRect();
          const canvas = document.querySelector('#diagnosticGraph .dg-svg').getBoundingClientRect();
          return Math.abs(card.x + card.width / 2 - canvas.x - canvas.width / 2) < 1
            && Math.abs(card.y + card.height / 2 - canvas.y - canvas.height / 2) < 1;
        }""")
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
        # A link can open a node whose ancestors were collapsed; reduced motion
        # reaches its final position without an intermediate frame.
        scale = page.evaluate("""() => {
          const controller = PgDiagGraphRender.render(document.querySelector('#diagnosticGraph'),
            pgDiagReport.diagnosticGraph, {collapsed: false});
          const scale = controller.state.view.scale;
          controller.select('disk.space');
          return scale;
        }""")
        page.locator('#diagnosticGraph').get_by_role('button', name='Full screen', exact=True).click()
        page.wait_for_selector('#diagnosticGraph .dg-svg[data-animating="false"]')
        centred = page.locator('#diagnosticGraph .dg-panel').evaluate("""panel => {
          const box = panel.getBoundingClientRect();
          const svg = document.querySelector('#diagnosticGraph .dg-svg');
          const canvas = svg.getBoundingClientRect();
          return {dx: box.x + box.width / 2 - canvas.x - canvas.width / 2,
            dy: box.y + box.height / 2 - canvas.y - canvas.height / 2,
            scale: svg.querySelector('.dg-scene').transform.baseVal.consolidate().matrix.a};
        }""")
        assert centred['dx'] == pytest.approx(0, abs=1)
        assert centred['dy'] == pytest.approx(0, abs=1)
        assert centred['scale'] == pytest.approx(scale)
        assert errors == []
        browser.close()
