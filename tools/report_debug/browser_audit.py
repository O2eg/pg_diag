"""Check a saved report with its embedded graph or current sources in memory."""

import argparse
import json
from pathlib import Path


from common import BUNDLE, GRAPH, inputs, sha256, write_json, check_output

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("reports", nargs="+", help="HTML files or quoted glob patterns")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument(
    "--current-source", action="store_true", help="Replace graph assets only in browser memory"
)
parser.add_argument(
    "--links",
    action="store_true",
    help="Inspect every selected-node link with cards open and closed",
)
parser.add_argument(
    "--animation", action="store_true", help="Also sample link geometry during card animation"
)
parser.add_argument(
    "--edges", action="store_true", help="Check solid parent-child routes as well as cross-links"
)
parser.add_argument(
    "--all-details", action="store_true", help="Also exercise two-step Expand all and simultaneous cards"
)
parser.add_argument(
    "--facts", action="store_true", help="Check fact-table borders, padding and overflow in all cards and both themes"
)
parser.add_argument(
    "--explain-button", action="store_true", help="Check the header shortcut with native clicks and active filters in both themes"
)
parser.add_argument("--node", action="append", help="Limit link checks to selected node IDs")
parser.add_argument(
    "--screenshots", type=Path, help="Save fitted branches; with --facts, also save unscaled selected cards in both themes"
)
parser.add_argument(
    "--evaluation", type=Path, help="Compare graph facts and scores with evaluate.cjs output"
)
args = parser.parse_args()
reports = inputs(args.reports, ".html")
check_output(args.output, reports)
expected = (
    {entry["path"]: entry for entry in json.loads(args.evaluation.read_text())}
    if args.evaluation
    else {}
)
if args.evaluation:
    check_output(args.output, [args.evaluation])
if args.output.resolve() in reports:
    parser.error("Output must differ from inputs")
results = []
# Parse arguments before loading the optional browser dependency.
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for path in reports:
        original = sha256(path)
        result = {
            "path": str(path),
            "errors": [],
            "link_cases": [],
            "mode": "current-source" if args.current_source else "embedded",
        }
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: result["errors"].append(str(error)))
        page.on(
            "console",
            lambda message: result["errors"].append(message.text)
            if message.type == "error"
            else None,
        )
        try:
            page.goto(path.as_uri(), wait_until="load", timeout=60000)
            page.wait_for_selector("#diagnosticGraph .dg-node", timeout=30000)
            if args.current_source:
                page.add_script_tag(
                    content="\n".join(
                        (GRAPH / name).read_text() for name in [*BUNDLE, "pg-diag-graph-render.js"]
                    )
                )
                page.evaluate(
                    '(css) => document.getElementById("pg-diag-graph-css").textContent = css',
                    (GRAPH / "pg-diag-graph.css").read_text(),
                )
                page.evaluate(
                    'definition => {pgDiagReport.diagnosticGraph = PgDiagGraph.evaluate(JSON.parse(document.getElementById("pg-diag-artifact").textContent), definition)}',
                    json.loads((GRAPH / "graph.json").read_text()),
                )
            page.evaluate("""() => {
              window.auditController = PgDiagGraphRender.render(document.getElementById('diagnosticGraph'), pgDiagReport.diagnosticGraph,
                {collapsed: false, onItemClick: id => pgDiagReport.navigateToItem(id)});
            }""")
            assert page.locator("#diagnosticGraph .dg-node").count() == 6
            result["coverage"] = page.evaluate("pgDiagReport.diagnosticGraph.coverage")
            if expected:
                reference = expected.get(str(path.with_suffix(".json")))
                assert reference is not None, "No companion JSON evaluation for " + str(path)
                actual = page.evaluate("pgDiagReport.diagnosticGraph.nodes")
                result["json_mismatches"] = [
                    [node_id, key]
                    for node_id, node in reference["nodes"].items()
                    for key in ["ownScore", "status", "facts", "reasons", "hints"]
                    if node_id not in actual or actual[node_id][key] != node[key]
                ]
                result["json_mismatches"].extend(
                    [[node_id, "extra-node"] for node_id in set(actual) - set(reference["nodes"])]
                )
            result["bad_navigation"] = page.evaluate("""() => {
              const ids = Object.keys(JSON.parse(document.getElementById('pg-diag-artifact').textContent).items);
              const bad = [];
              for (const id of ids) {
                pgDiagReport.navigateToItem(id);
                const item = document.getElementById('item-' + id);
                if (!item || !item.open || item.closest('.hidden')) bad.push(id);
              }
              return bad;
            }""")
            # Exercise lazy charts and at least one auto_explain plan per format.
            result["plans"] = page.evaluate("""() => {
              for (const details of document.querySelectorAll('details')) details.open = true;
              window.dispatchEvent(new Event('resize'));
              const result = {};
              const chart = echartsCharts.find(entry => entry.item.item_id === 'server_log.auto_explain_plans');
              if (chart) for (const series of chart.chart.getOption().series) for (const point of series.data || []) {
                const format = point.pgDiagViewer?.plan_format;
                if (!format || result[format]) continue;
                openQueryPlanViewerFromChart({data: point});
                result[format] = {rows: document.querySelectorAll('#planViewerModal tr.pv-row').length,
                  error: document.querySelector('#planViewerModal .plan-viewer-error')?.textContent || null};
              }
              return result;
            }""")
            # Close any modal before graph checks; the browser APIs below inspect SVG directly.
            page.keyboard.press("Escape")
            if args.explain_button:
                result["explain_button"] = []
                button = page.locator("#explainAvailable")
                assert button.count() == 1, "Explain shortcut is missing from the report template"
                for theme in ["light", "dark"]:
                    page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                    page.evaluate("window.scrollTo(0, 0)")
                    if args.screenshots:
                        args.screenshots.mkdir(parents=True, exist_ok=True)
                        screenshot = args.screenshots / (path.stem + "-header-" + theme + ".png")
                        page.locator(".app-header").screenshot(path=str(screenshot))
                    entry = {"theme": theme, "visible": button.is_visible()}
                    if entry["visible"]:
                        page.evaluate("""() => {
                          const item = findItemElement('server_log.auto_explain_plans');
                          setDetailsOpen(item, false, false);
                          setDetailsOpen(item.closest('details.section'), false, false);
                        }""")
                        page.locator("#itemSearch").fill("no-matching-explain-item")
                        button.click()
                        page.wait_for_function("""() => {
                          const item = findItemElement('server_log.auto_explain_plans');
                          return item.open && item.closest('details.section').open
                            && !item.closest('.hidden') && document.activeElement === directSummary(item);
                        }""")
                        entry["navigated"] = page.evaluate("""() => {
                          const summary = directSummary(findItemElement('server_log.auto_explain_plans'));
                          return summary.getBoundingClientRect().top >= 0
                            && summary.getBoundingClientRect().top < innerHeight
                            && document.getElementById('itemSearch').value === '';
                        }""")
                        assert entry["navigated"], "Explain shortcut did not scroll to the item or reset filters"
                    result["explain_button"].append(entry)
            if args.facts:
                result["fact_tables"] = []
                for theme in ["light", "dark"]:
                    page.evaluate("""theme => {
                      document.documentElement.dataset.theme = theme;
                      auditController.collapseAll();
                      auditController.expandAll();
                      auditController.expandAll();
                    }""", theme)
                    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                    entry = page.evaluate("""() => {
                      const problems = [], tables = document.querySelectorAll('#diagnosticGraph .dg-detail .dg-facts');
                      let cells = 0;
                      for (const table of tables) {
                        const card = table.closest('.dg-detail'), panel = table.closest('.dg-panel');
                        const fail = (kind, text) => problems.push({node: card.dataset.nodeId, kind, text});
                        if (panel.scrollWidth > panel.clientWidth + 1 || table.scrollWidth > table.clientWidth + 1)
                          fail('table-overflow');
                        if (panel.offsetHeight > Number(card.getAttribute('height')) + 1) fail('clipped-card');
                        for (const cell of table.querySelectorAll('th, td')) {
                          cells++;
                          const style = getComputedStyle(cell);
                          if (cell.scrollWidth > cell.clientWidth + 1) fail('cell-overflow', cell.textContent);
                          for (const edge of ['Top', 'Right', 'Bottom', 'Left']) {
                            if (parseFloat(style['border' + edge + 'Width']) < 1 || style['border' + edge + 'Style'] === 'none')
                              fail('missing-border-' + edge, cell.textContent);
                            if (parseFloat(style['padding' + edge]) < 6) fail('missing-padding-' + edge, cell.textContent);
                          }
                          if (cell.tagName === 'TH') {
                            const share = cell.getBoundingClientRect().width / table.getBoundingClientRect().width;
                            if (share < 0.35 || share > 0.55) fail('unbalanced-columns', cell.textContent);
                          }
                        }
                      }
                      return {tables: tables.length, cells, problems};
                    }""")
                    result["fact_tables"].append({"theme": theme, **entry})
                    # Isolate the existing card at its actual width for a readable CSS screenshot.
                    if args.screenshots and args.node:
                        args.screenshots.mkdir(parents=True, exist_ok=True)
                        for node_id in args.node:
                            page.evaluate("""id => {
                              const panel = document.querySelector(`.dg-detail[data-node-id="${id}"] .dg-panel`);
                              if (!panel) throw new Error('Unknown card: ' + id);
                              const preview = document.createElement('div');
                              preview.id = 'audit-card-preview'; preview.className = 'dg';
                              preview.style.cssText = `position:fixed;left:0;top:0;width:${panel.offsetWidth}px;z-index:99999;margin:0;border:0;border-radius:0`;
                              preview.appendChild(panel.cloneNode(true)); document.body.appendChild(preview);
                            }""", node_id)
                            try:
                                screenshot = args.screenshots / (path.stem + "-" + node_id + "-" + theme + "-card.png")
                                page.locator("#audit-card-preview").screenshot(path=str(screenshot))
                            finally:
                                page.evaluate("document.getElementById('audit-card-preview').remove()")
                print("Checked fact tables in both themes", flush=True)
            if args.links or args.edges or args.all_details:
                page.add_script_tag(
                    content=(Path(__file__).with_name("browser_routes.js")).read_text()
                )
                page.evaluate("edges => window.auditEdges = edges", args.edges or args.all_details)
                selected = page.evaluate(
                    "pgDiagReport.diagnosticGraph.order" if args.edges or args.all_details else
                    "[...new Set(pgDiagReport.diagnosticGraph.links.flatMap(link => [link.from, link.to]))]"
                )
                if args.node:
                    assert set(args.node) <= set(
                        selected
                    ), "Unknown node or node has no requested links"
                    selected = args.node
                for theme in ["light", "dark"]:
                    page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                    for node_id in selected:
                        for mode in (["branches", "all", "cards"] if args.all_details else ["branches", "all"]):
                            for card in [True, False]:
                                entry = page.evaluate(
                                    """({id, mode, card}) => {
                                  auditController.collapseAll();
                                  if (mode !== 'branches') auditController.expandAll();
                                  if (mode === 'cards') auditController.expandAll();
                                  auditController.select(id);
                                  if (!card) document.querySelector(`.dg-detail[data-node-id="${id}"] .dg-panel-close`).click();
                                  const result = inspectGraphLinks({edges: auditEdges});
                                  const expected = mode === 'cards' ? pgDiagReport.diagnosticGraph.order.length - (card ? 0 : 1) : (card ? 1 : 0);
                                  result.cards = document.querySelectorAll('#diagnosticGraph .dg-detail').length;
                                  if (result.cards !== expected) result.problems.push({kind: 'card-count', expected, actual: result.cards});
                                  return result;
                                }""",
                                    {"id": node_id, "mode": mode, "card": card},
                                )
                                result["link_cases"].append(
                                    {"theme": theme, "mode": mode, "card": card, **entry}
                                )
                                if args.screenshots and theme == "dark" and mode == "branches" and card:
                                    args.screenshots.mkdir(parents=True, exist_ok=True)
                                    page.evaluate("auditController.fit()")
                                    screenshot = args.screenshots / (path.stem + "-" + node_id + ".png")
                                    page.locator("#diagnosticGraph .dg-canvas").screenshot(path=str(screenshot))
                        print(f"{theme}: checked links for {node_id}", flush=True)
                if args.animation:
                    page.emulate_media(reduced_motion="no-preference")
                    # Start from a settled fully expanded graph and sample moving cards.
                    page.evaluate("auditController.collapseAll(); auditController.expandAll()")
                    page.wait_for_selector('#diagnosticGraph .dg-svg[data-animating="false"]')
                    for node_id in selected:
                        samples = page.evaluate(
                            """id => new Promise(resolve => {
                          auditController.select(id); const samples = [];
                          function sample() {
                            samples.push(inspectGraphLinks({edges: auditEdges}));
                            if (document.querySelector('.dg-svg').dataset.animating === 'false') resolve(samples);
                            else requestAnimationFrame(sample);
                          }
                          requestAnimationFrame(sample);
                        })""",
                            node_id,
                        )
                        result["link_cases"].extend(
                            {"mode": "animation", **entry} for entry in samples
                        )
                    if args.all_details:
                        samples = page.evaluate("""async () => {
                          const samples = [];
                          const settle = async label => {
                            do {
                              await new Promise(requestAnimationFrame);
                              samples.push({...inspectGraphLinks({edges: true}), phase: label});
                            } while (document.querySelector('.dg-svg').dataset.animating === 'true');
                          };
                          auditController.expandAll();
                          await settle('open-all-cards');
                          auditController.collapseAll();
                          await settle('collapse-all-cards');
                          auditController.expandAll();
                          await new Promise(resolve => setTimeout(resolve, 30));
                          auditController.expandAll();
                          await new Promise(resolve => setTimeout(resolve, 30));
                          auditController.collapseAll();
                          await settle('interrupted-all-cards');
                          return samples;
                        }""")
                        result["link_cases"].extend(
                            {"mode": "bulk-animation", **entry} for entry in samples
                        )
            result["passed"] = (
                not result["bad_navigation"]
                and not result.get("json_mismatches")
                and not result["coverage"]["unboundItems"]
                and not result["errors"]
                and all(not entry["problems"] for entry in result.get("fact_tables", []))
                and all(not entry["problems"] for entry in result["link_cases"])
                and all(plan["rows"] > 0 and not plan["error"] for plan in result["plans"].values())
            )
        except Exception as error:
            result.update(passed=False, failure=repr(error))
        finally:
            result["unchanged"] = sha256(path) == original
            result["sha256"] = original
            results.append(result)
            write_json(args.output, results)
            print(
                json.dumps(
                    {
                        "report": str(path),
                        "passed": result.get("passed"),
                        "link_cases": len(result["link_cases"]),
                        "link_problems": sum(
                            bool(entry["problems"]) for entry in result["link_cases"]
                        ),
                        "errors": result["errors"],
                    }
                ),
                flush=True,
            )
            page.close()
    browser.close()
raise SystemExit(
    0 if all(result.get("passed") and result["unchanged"] for result in results) else 1
)
