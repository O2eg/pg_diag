"""Diagnostic graph: graph.json contract, catalog coverage, HTML integration, node tests."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from pg_diag.content_loader import load_content
from pg_diag.metric_engine import build_chart_result
from pg_diag.presentation import apply_presentation_contract
from pg_diag.render.html import render_html
from pg_diag.versioning import select_query_variant

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIR = ROOT / "src" / "pg_diag" / "render" / "graph"
FIXTURES = ROOT / "tests" / "data" / "diagnostic_graph"
ROOTS = ["cpu", "ram", "disk", "network", "database_health", "database_security"]
ROLES = {"primary", "support", "fact"}
REQUIREMENTS = {
    "snapshots",
    "host",
    "log",
    "pg_stat_statements",
    "pg_stat_kcache",
    "pg_wait_sampling",
    "pg_buffercache",
}


def _graph() -> dict:
    return json.loads((GRAPH_DIR / "graph.json").read_text(encoding="utf-8"))


def _catalog_item_ids() -> set[str]:
    report = yaml.safe_load(
        (ROOT / "src" / "pg_diag" / "content" / "report.yaml").read_text(encoding="utf-8")
    )
    return {
        f"{section_id}.{item_id}"
        for section_id, section in report["sections"].items()
        for item_id in (section.get("items") or {})
    }


def _engine_evaluator_names() -> set[str]:
    source = (GRAPH_DIR / "pg-diag-graph-rules.js").read_text(encoding="utf-8")
    return set(re.findall(r"^    ([a-z_]+)\((?:ctx)?\) \{", source, re.M))


def test_graph_definition_is_a_tree_with_six_roots() -> None:
    graph = _graph()
    assert graph["schema_version"] == 1
    assert graph["roots"] == ROOTS
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert len(nodes) == len(graph["nodes"]), "duplicate node ids"
    for node_id, node in nodes.items():
        if node_id in ROOTS:
            assert "parent" not in node
        else:
            assert node["parent"] in nodes, f"{node_id}: unknown parent"
        assert node["label"].strip()
        assert node["summary"].strip()
        if "pressure" in node:
            assert node["pressure"] in {"cpu_user", "cpu_system", "cpu_iowait", "ram", "disk"}
        for requirement in node.get("requires", []):
            assert requirement in REQUIREMENTS, f"{node_id}: unknown requirement {requirement}"
        for binding in node["bindings"]:
            assert binding["role"] in ROLES, f"{node_id}: bad role in {binding}"
            if "weight" in binding:
                assert 0 < binding["weight"] <= 1
    # acyclic parent chain
    for node_id in nodes:
        seen = set()
        cursor = node_id
        while cursor:
            assert cursor not in seen, f"parent cycle at {cursor}"
            seen.add(cursor)
            cursor = nodes[cursor].get("parent")
    for link in graph["links"]:
        assert link["from"] in nodes and link["to"] in nodes, f"dangling link {link}"
        assert link["from"] != link["to"]


def test_every_catalog_item_is_bound_and_every_binding_exists() -> None:
    graph = _graph()
    catalog = _catalog_item_ids()
    bound = {binding["id"] for node in graph["nodes"] for binding in node["bindings"]}
    assert not (catalog - bound), f"catalog items without a graph node: {sorted(catalog - bound)}"
    assert not (
        bound - catalog
    ), f"graph bindings missing in the catalog: {sorted(bound - catalog)}"


def test_every_node_evaluator_exists_in_the_engine() -> None:
    graph = _graph()
    names = _engine_evaluator_names()
    for node in graph["nodes"]:
        evaluator = node.get("evaluator", "generic")
        assert evaluator in names, f"{node['id']}: evaluator {evaluator} is not implemented"


def test_every_network_tagged_item_is_bound_under_network() -> None:
    report = yaml.safe_load((ROOT / "src/pg_diag/content/report.yaml").read_text())
    expected = {
        f"{sid}.{iid}"
        for sid, section in report["sections"].items()
        for iid, item in section["items"].items()
        if "Network" in item.get("tags", [])
    }
    nodes = {node["id"]: node for node in _graph()["nodes"]}
    bound = set()
    for node in nodes.values():
        ancestor = node
        while ancestor.get("parent"):
            ancestor = nodes[ancestor["parent"]]
        if ancestor["id"] == "network":
            bound.update(binding["id"] for binding in node["bindings"])
    assert expected <= bound, expected - bound
    assert {
        "activity_locks.wait_events", "replication.physical_replication",
        "server_log.replication_events", "sql_workload.top_sql_by_calls",
        "snapshot_delta_workload.database_session_outcomes_delta",
        "cluster_inventory.unix_socket_permissions",
    } <= bound


def test_report_html_embeds_the_graph_module() -> None:
    artifact = json.loads(
        (FIXTURES / "lab_one_shot_remote_db_only.json").read_text(encoding="utf-8")
    )
    artifact.setdefault("query_texts", {})
    artifact.setdefault("object_ddl", {})
    artifact.setdefault("snapshots", [])
    artifact.setdefault("snapshot_schemas", {})
    artifact.setdefault("content", {"document": {"field_reference": {}}, "provenance": {}})
    html = render_html(artifact, validate=False)
    for marker in (
        'id="pg-diag-graph-css"',
        'id="pg-diag-graph-definition"',
        'id="pg-diag-graph-library"',
        'id="pg-diag-graph-render-library"',
        'id="diagnosticGraph"',
        "window.PgDiagGraph.evaluate(",
        "navigateToItem",
    ):
        assert marker in html, marker
    assert "__PG_DIAG_GRAPH" not in html
    assert (
        html.index("root.PgDiagGraphData = factory")
        < html.index("root.PgDiagGraphRules = factory")
        < html.index("root.PgDiagGraph = factory")
    )

    class StylesParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.styles: dict[str, str] = {}
            self.current_style: str | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "style":
                self.current_style = dict(attrs).get("id") or "anonymous"
                self.styles.setdefault(self.current_style, "")

        def handle_data(self, data: str) -> None:
            if self.current_style is not None:
                self.styles[self.current_style] += data

        def handle_endtag(self, tag: str) -> None:
            if tag == "style":
                self.current_style = None

    styles = StylesParser()
    styles.feed(html)
    assert "pg-diag-graph-css" in styles.styles
    assert "--dg-edge:" in styles.styles["pg-diag-graph-css"]
    assert all("<style" not in css.lower() for css in styles.styles.values())
    definition_start = html.index('id="pg-diag-graph-definition"')
    definition_end = html.index("</script>", definition_start)
    embedded = json.loads(html[html.index(">", definition_start) + 1 : definition_end])
    assert embedded["roots"] == ROOTS


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_node_test_suite_passes() -> None:
    # Node 22 treats a positional directory as a module, unlike Node 18.
    # Expand the files here so the same invocation works on both versions.
    test_files = sorted((ROOT / "tests" / "js").rglob("*.test.js"))
    assert test_files, "no JavaScript tests found"
    result = subprocess.run(
        ["node", "--test", *(str(path) for path in test_files)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]


def _collected_metric(content_path: Path, metric_id: str, samples: list[dict]) -> dict:
    content = load_content(content_path)
    metric = content.metrics[metric_id]
    query = content.queries[metric["source_query"]]
    selected = select_query_variant(query["title"], query, 180000)
    result = build_chart_result(metric, samples, selected.variant["semantic_columns"])
    item = {
        "collection_status": "ok",
        "source_kind": "metric",
        "source_metadata": {"metric_id": metric_id},
        "result": result,
    }
    apply_presentation_contract(content, {"items": {"test.metric": item}})
    return item


def _evaluate_graph(artifact: dict) -> dict:
    result = subprocess.run(
        ["node", "-e", """
const fs = require('node:fs');
const G = require('./src/pg_diag/render/graph/pg-diag-graph.js');
const definition = require('./src/pg_diag/render/graph/graph.json');
console.log(JSON.stringify(G.evaluate(JSON.parse(fs.readFileSync(0, 'utf8')), definition).nodes));
"""],
        input=json.dumps(artifact),
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
        check=True,
    )
    nodes = json.loads(result.stdout)
    assert not {node_id: node["error"] for node_id, node in nodes.items() if node["error"]}
    return nodes


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_graph_counts_deadlocks_from_one_collected_interval(content_path: Path) -> None:
    samples = [
        {
            "timestamp": f"2026-09-05T00:00:{index * 30:02d}Z",
            "rows": [{"datname": "test", "deadlocks": index * 100}],
        }
        for index in range(2)
    ]
    item = _collected_metric(content_path, "database.deadlocks", samples)
    source = "snapshot_charts_db.database_deadlocks"
    artifact = {
        "runtime": {
            "mode": "snapshots",
            "snapshot_window_started_at": samples[0]["timestamp"],
            "snapshot_window_finished_at": samples[-1]["timestamp"],
        },
        "items": {source: item},
    }
    nodes = _evaluate_graph(artifact)
    assert nodes["health.locks"]["ownScore"] == 1
    assert nodes["database_health"]["status"] == "crit"
    assert source in nodes["health.locks"]["evidence"]
    assert any("100 deadlock(s)" in reason for reason in nodes["health.locks"]["reasons"])


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_graph_preserves_waits_when_collected_top_n_members_change(content_path: Path) -> None:
    samples = []
    for index in range(6):
        waiting = index < 3
        samples.append({
            "timestamp": f"2026-09-05T00:00:{index * 5:02d}Z",
            "rows": [{
                "datname": "test",
                "wait_event_type": "LWLock" if waiting else "Not waiting",
                "wait_event": "BufferContent" if waiting else "Active without wait event",
                "query_id": "1" if waiting else "2",
                "sessions": 30 if waiting else 1,
            }],
        })
    profile = _collected_metric(content_path, "activity.wait_sample_profile", samples)
    source = "activity_locks.wait_event_sample_profile"
    nodes = _evaluate_graph({"items": {
        source: profile,
        "activity_locks.wait_events": {
            "collection_status": "ok",
            "result": {
                "kind": "table",
                "columns": [{"name": "wait_event_type"}, {"name": "sessions"}],
                "rows": [["Not waiting", 1]],
            },
        },
        "snapshot_charts_os.os_cpu_utilization": {
            "collection_status": "ok",
            "result": {"kind": "chart", "series": [{
                "name": "system",
                "points": [{"t": sample["timestamp"], "value": 50} for sample in samples],
            }]},
        },
    }})
    assert nodes["cpu.contention"]["ownScore"] == 1
    assert source in nodes["cpu.contention"]["evidence"]
    assert any("p95 30.0 sessions" in reason for reason in nodes["cpu.contention"]["reasons"])
