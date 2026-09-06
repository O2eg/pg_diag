import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path


parser = argparse.ArgumentParser(
    description="Click every report-item link through graph nodes in a saved HTML."
)
parser.add_argument("report", type=Path)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--expected-items", type=int)
parser.add_argument("--node", help="Check links specifically from this node's card")
parser.add_argument(
    "--item", action="append", help="Limit actual clicks to these item IDs (repeatable)."
)
args = parser.parse_args()
TARGET = args.report.resolve()
RESULT = args.output.resolve()
if RESULT in {TARGET, TARGET.with_suffix(".json")}:
    parser.error("Output must differ from the input report and its JSON companion")
RESULT.parent.mkdir(parents=True, exist_ok=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


hashes = {
    str(path): digest(path) for path in (TARGET, TARGET.with_suffix(".json")) if path.is_file()
}
started = time.monotonic()
result = {
    "report": str(TARGET),
    "method": "Native Playwright pointer clicks on graph ancestors, node circles and report-item buttons in the original HTML; no injected renderer or navigation calls.",
    "viewport": {"width": 1600, "height": 1000},
    "errors": [],
    "items": [],
}


def save():
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


# Parse arguments before loading the optional browser dependency.
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport=result["viewport"], reduced_motion="reduce")
    page.set_default_timeout(7000)
    page.on("pageerror", lambda error: result["errors"].append(str(error)))
    page.on(
        "console",
        lambda message: result["errors"].append(message.text) if message.type == "error" else None,
    )
    page.goto(TARGET.as_uri(), wait_until="load", timeout=60000)
    page.wait_for_selector("#diagnosticGraph .dg-node")
    graph = page.locator("#diagnosticGraph")
    evaluation = page.evaluate("pgDiagReport.diagnosticGraph")
    item_ids = page.evaluate(
        'Object.keys(JSON.parse(document.getElementById("pg-diag-artifact").textContent).items)'
    )
    dom_ids = page.locator("details.item").evaluate_all(
        "items => items.map(item => item.dataset.itemId)"
    )
    assert len(item_ids) == len(dom_ids) and set(item_ids) == set(dom_ids)
    if args.expected_items is not None:
        assert len(item_ids) == args.expected_items, (len(item_ids), args.expected_items)
    if TARGET.with_suffix(".json").is_file():
        json_ids = list(json.loads(TARGET.with_suffix(".json").read_text())["items"])
        assert set(item_ids) == set(json_ids)
    artifact_count = len(item_ids)
    if args.item:
        assert set(args.item) <= set(item_ids), "Unknown requested item ID"
        item_ids = list(dict.fromkeys(args.item))
    assert item_ids, "No items to check"
    expected_count = len(item_ids)
    assert graph.locator(".dg-node").count() == 6
    nodes = evaluation["nodes"]
    roots = evaluation["roots"]
    reachable = set()

    def visit(node_id):
        assert node_id not in reachable, ("duplicate/cyclic tree", node_id)
        reachable.add(node_id)
        for child_id in nodes[node_id]["children"]:
            assert nodes[child_id]["parent"] == node_id
            visit(child_id)

    for root_id in roots:
        visit(root_id)
    assert reachable == set(nodes)

    def route(node_id):
        chain = []
        while node_id:
            chain.append(node_id)
            node_id = nodes[node_id]["parent"]
        return list(reversed(chain))

    bindings = defaultdict(list)
    absent = set()
    for node in nodes.values():
        for binding in node["bindings"]:
            if binding["presence"] == "absent":
                absent.add(binding["id"])
            else:
                bindings[binding["id"]].append((node["id"], binding))
    assert not (set(item_ids) - set(bindings)), ("unbound", set(item_ids) - set(bindings))
    assert not (set(item_ids) & absent)
    if args.node:
        assert args.node in nodes, "Unknown graph node"
        card_items = {
            binding["id"]
            for binding in nodes[args.node]["bindings"]
            if binding["presence"] != "absent"
        }
        if args.item:
            assert set(item_ids) <= card_items, "Requested item is not linked from this card"
        else:
            item_ids = [item_id for item_id in item_ids if item_id in card_items]
        assert item_ids, "Card has no available report-item links"
        expected_count = len(item_ids)
    groups = defaultdict(list)
    for item_id in item_ids:
        node_id, binding = min(
            [pair for pair in bindings[item_id] if not args.node or pair[0] == args.node],
            key=lambda pair: (len(route(pair[0])), len(nodes[pair[0]]["bindings"]), pair[0]),
        )
        groups[node_id].append(binding)
    result.update(
        {
            "artifact_items": artifact_count,
            "requested_items": expected_count,
            "dom_items": len(dom_ids),
            "initial_root_circles": 6,
            "reachable_graph_nodes": len(reachable),
            "cards_visited": len(groups),
            "catalog_ids_absent_from_report": sorted(absent),
        }
    )
    print(json.dumps({k: v for k, v in result.items() if k not in ("items", "errors")}), flush=True)

    def settle():
        page.wait_for_selector('#diagnosticGraph .dg-svg[data-animating="false"]')

    def control(name):
        graph.get_by_role("button", name=name, exact=True).click()
        settle()

    def open_card(node_id):
        control("Collapse all")
        for step in route(node_id):
            graph.locator(".dg-node[data-node-id=" + json.dumps(step) + "]").click()
            settle()
            control("Fit graph")
        assert graph.locator(
            ".dg-detail[data-node-id=" + json.dumps(node_id) + "] .dg-panel"
        ).is_visible()

    def click_item(node_id, binding):
        item_id = binding["id"]
        button = graph.locator(
            ".dg-detail[data-node-id="
            + json.dumps(node_id)
            + "] .dg-item[data-item-id="
            + json.dumps(item_id)
            + "]"
        )
        assert button.count() == 1 and button.is_enabled()
        button.click()
        page.wait_for_function(
            """id => {
          const item = document.getElementById('item-' + id);
          return item && item.open && document.activeElement === item.querySelector(':scope > summary');
        }""",
            arg=item_id,
        )
        checked = page.evaluate(
            """id => {
          const item = document.getElementById('item-' + id);
          const ancestors = []; let parent = item.parentElement;
          while (parent) {if (parent.tagName === 'DETAILS') ancestors.push(parent.open); parent = parent.parentElement;}
          const rect = item.querySelector(':scope > summary').getBoundingClientRect();
          return {
            target_id: item.dataset.itemId, open: item.open,
            ancestors_open: ancestors.every(Boolean), hidden: !!item.closest('.hidden'),
            summary_in_viewport: rect.bottom > 0 && rect.top < innerHeight,
            focus_matches: document.activeElement === item.querySelector(':scope > summary'),
          };
        }""",
            item_id,
        )
        assert checked["target_id"] == item_id and checked["open"] and checked["ancestors_open"]
        assert (
            checked["summary_in_viewport"] and checked["focus_matches"] and not checked["hidden"]
        ), checked
        return {
            "item_id": item_id,
            "node_id": node_id,
            "path": route(node_id),
            "presence": binding["presence"],
            "collection_status": binding.get("collection_status"),
            "passed": True,
            **checked,
        }

    try:
        for group_index, (node_id, node_bindings) in enumerate(groups.items(), 1):
            open_card(node_id)
            for binding in node_bindings:
                result["items"].append(click_item(node_id, binding))
            save()
            if group_index % 10 == 0 or group_index == len(groups):
                print(
                    f"Clicked {len(result['items'])}/{expected_count} items; {group_index}/{len(groups)} cards; {time.monotonic()-started:.1f}s",
                    flush=True,
                )
        assert len(result["items"]) == expected_count
        assert len({item["item_id"] for item in result["items"]}) == expected_count
        # Verify the same link recovers an item hidden by active report filters.
        node_id, node_bindings = next(iter(groups.items()))
        open_card(node_id)
        search = page.locator("#itemSearch")
        search.fill("__graph_navigation_no_item_matches__")
        page.wait_for_function(
            'document.querySelectorAll("details.item:not(.hidden)").length === 0'
        )
        click_item(node_id, node_bindings[0])
        assert search.input_value() == ""
        result["filtered_navigation"] = "passed"
        # Full-screen navigation must restore the report before opening the item.
        open_card(node_id)
        control("Full screen")
        click_item(node_id, node_bindings[0])
        assert graph.locator("dialog.dg-fullscreen").evaluate("dialog => !dialog.open")
        assert not graph.locator("dialog.dg-fullscreen .dg-canvas").count()
        assert page.locator("html").evaluate('element => element.style.overflow !== "hidden"')
        result["fullscreen_navigation"] = "passed"
        control("Collapse all")
        assert graph.locator(".dg-node").count() == 6
        assert not result["errors"], result["errors"]
        result["passed"] = True
    except Exception as error:
        result["passed"] = False
        result["failure"] = repr(error)
        page.screenshot(path=str(RESULT.with_suffix(".failure.png")))
        raise
    finally:
        result["presence_counts"] = dict(Counter(item["presence"] for item in result["items"]))
        result["duration_seconds"] = round(time.monotonic() - started, 1)
        result["source_files"] = {
            path: {"sha256": original, "unchanged": digest(Path(path)) == original}
            for path, original in hashes.items()
        }
        save()
        browser.close()
print(
    json.dumps({k: v for k, v in result.items() if k != "items"}, ensure_ascii=False, indent=2),
    flush=True,
)
