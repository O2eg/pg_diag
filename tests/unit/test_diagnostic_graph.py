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

from pg_diag.render.html import render_html

ROOT = Path(__file__).resolve().parents[2]
GRAPH_DIR = ROOT / "src" / "pg_diag" / "render" / "graph"
FIXTURES = ROOT / "tests" / "data" / "diagnostic_graph"
ROOTS = ["cpu", "ram", "disk", "database_health", "database_security"]
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
    source = (GRAPH_DIR / "pg-diag-graph.js").read_text(encoding="utf-8")
    names = set(re.findall(r"^    ([a-z_]+)\(ctx\) \{", source, re.M))
    names.update(re.findall(r"evaluators\.([a-z_]+) = ", source))
    names.update({"aggregate", "generic"})
    # names assigned in the registry loop from causeEvaluators
    names.update(name for name in re.findall(r"^    ([a-z_]+)\(ctx\) \{", source, re.M))
    return names


def test_graph_definition_is_a_tree_with_five_roots() -> None:
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
    result = subprocess.run(
        ["node", "--test", str(ROOT / "tests" / "js")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
