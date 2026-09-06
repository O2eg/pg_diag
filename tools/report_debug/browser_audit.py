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
parser.add_argument("--node", action="append", help="Limit link checks to selected node IDs")
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
            if args.links:
                page.add_script_tag(
                    content=(Path(__file__).with_name("browser_routes.js")).read_text()
                )
                selected = page.evaluate(
                    "[...new Set(pgDiagReport.diagnosticGraph.links.flatMap(link => [link.from, link.to]))]"
                )
                if args.node:
                    assert set(args.node) <= set(
                        selected
                    ), "Unknown node or node has no cross-links"
                    selected = args.node
                for theme in ["light", "dark"]:
                    page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                    for node_id in selected:
                        for mode in ["branches", "all"]:
                            for card in [True, False]:
                                entry = page.evaluate(
                                    """({id, mode, card}) => {
                                  if (mode === 'all') auditController.expandAll(); else auditController.collapseAll();
                                  auditController.select(id);
                                  if (!card) document.querySelector('.dg-panel-close').click();
                                  return inspectGraphLinks();
                                }""",
                                    {"id": node_id, "mode": mode, "card": card},
                                )
                                result["link_cases"].append(
                                    {"theme": theme, "mode": mode, "card": card, **entry}
                                )
                        print(f"{theme}: checked links for {node_id}", flush=True)
                if args.animation:
                    page.emulate_media(reduced_motion="no-preference")
                    # Start from a settled fully expanded graph and sample moving cards.
                    page.evaluate("auditController.expandAll()")
                    page.wait_for_selector('#diagnosticGraph .dg-svg[data-animating="false"]')
                    for node_id in selected:
                        samples = page.evaluate(
                            """id => new Promise(resolve => {
                          auditController.select(id); const samples = [];
                          function sample() {
                            samples.push(inspectGraphLinks());
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
            result["passed"] = (
                not result["bad_navigation"]
                and not result.get("json_mismatches")
                and not result["coverage"]["unboundItems"]
                and not result["errors"]
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
