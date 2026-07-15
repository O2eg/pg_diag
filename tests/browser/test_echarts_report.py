from __future__ import annotations

import os
from pathlib import Path

import pytest

from pg_diag import runtime_config
from pg_diag.artifact import strip_artifact_metadata
from pg_diag.render.html import render_html


pytestmark = pytest.mark.skipif(
    os.environ.get("PG_DIAG_BROWSER_TESTS") != "1",
    reason="set PG_DIAG_BROWSER_TESTS=1 to run Playwright renderer tests",
)


def _chart_result(kind: str, values: list[list[float]], *, names: list[str]) -> dict:
    timestamps = [
        "2026-07-15T10:00:00Z",
        "2026-07-15T10:00:05Z",
        "2026-07-15T10:00:10Z",
    ]
    return {
        "kind": "chart",
        "chart": {"kind": kind, "x_type": "datetime", "unit": "count/s"},
        "series": [
            {
                "name": name,
                "unit": "count/s",
                "points": [
                    {"t": timestamp, "value": value}
                    for timestamp, value in zip(timestamps, series_values, strict=True)
                ],
            }
            for name, series_values in zip(names, values, strict=True)
        ],
    }


def _artifact() -> dict:
    item_definitions = {
        "line": {"metric": "test.line", "tags": ["SQL"]},
        "area": {"metric": "test.area", "tags": ["CPU"]},
        "columns": {"metric": "test.columns", "tags": ["Tables"]},
    }
    column_names = [f"schema.table_with_a_long_descriptive_name_{index}" for index in range(30)]
    results = {
        "charts.line": _chart_result(
            "line", [[120_000, 140_000, 130_000]], names=["query.123"]
        ),
        "charts.area": _chart_result(
            "stacked_area", [[2, 4, 3], [1, 2, 1]], names=["read", "write"]
        ),
        "charts.columns": _chart_result(
            "stacked_column",
            [[index + 1, index + 2, index + 3] for index in range(len(column_names))],
            names=column_names,
        ),
    }
    items = {}
    for item_key, definition in item_definitions.items():
        item_id = f"charts.{item_key}"
        items[item_id] = {
            "item_id": item_id,
            "section_id": "charts",
            "item_key": item_key,
            "title": item_key.title(),
            "source_kind": "metric",
            "collection_scope": "post_collection",
            "collection_status": "ok",
            "severity_level": "ok",
            "state": "expanded",
            "result": results[item_id],
            "source_metadata": {
                "metric_id": definition["metric"],
                "chart": results[item_id]["chart"],
                "tags": definition["tags"],
            },
            "diagnostics": [],
            "issues": {},
        }

    return {
        "artifact_schema_version": runtime_config.ARTIFACT_SCHEMA_VERSION,
        "generator": {"name": "pg_diag", "version": "0.9.0"},
        "content": {
            "schema_version": runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION,
            "content_path": "/tmp/test-content",
            "checksum": "sha256:test",
            "report_id": "echarts-browser-test",
            "document": {
                "report": {"id": "echarts-browser-test", "title": "ECharts Browser Test"},
                "runtime_policy": {},
                "defaults": {"table": {"page_size": 25}},
                "sections": {"charts": {"title": "Charts", "items": item_definitions}},
                "catalogs": {"queries": {}, "presentation": {"units": {}}},
                "queries": {},
                "scripts": {},
                "metrics": {},
                "python_sources": {},
                "sampler_providers": {},
                "field_reference": {},
            },
            "provenance": {"report": ["report.yaml"], "sections": ["report.yaml"]},
        },
        "report": {"id": "echarts-browser-test", "title": "ECharts Browser Test"},
        "runtime": {
            "mode": "snapshots",
            "collection_mode": "remote-db-only",
            "database_name": "postgres",
            "started_at": "2026-07-15T10:00:00Z",
            "finished_at": "2026-07-15T10:00:10Z",
            "duration_seconds": 10,
            "interval_seconds": 5,
        },
        "display": {"table": {"page_size": 25}},
        "sections": [
            {
                "section_id": "charts",
                "title": "Charts",
                "state": "expanded",
                "items": list(items),
            }
        ],
        "items": items,
        "query_texts": {"123": "select count(*) from pg_stat_activity"},
        "snapshot_schemas": {},
        "snapshots": [],
        "diagnostics": [],
    }


def test_self_contained_echarts_report_in_browser(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    report_path = tmp_path / "report.html"
    report_path.write_text(render_html(_artifact(), validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        errors: list[str] = []
        external_requests: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: external_requests.append(request.url)
            if request.url.startswith(("http://", "https://"))
            else None,
        )

        page.goto(report_path.as_uri(), wait_until="load")
        page.wait_for_function(
            "document.querySelectorAll('[data-chart-ready=true]').length === 3"
        )
        state = page.evaluate(
            """() => {
              const entry = echartsCharts[0];
              entry.chart.resize();
              enableEChartsPan(entry);
              return {
                ready: document.querySelectorAll("[data-chart-ready=true]").length,
                svgs: document.querySelectorAll(".echarts-chart svg").length,
                renderer: entry.chart.getZr().painter.getType(),
                zoom: entry.zoomRange,
                svgDataUrl: entry.chart.getDataURL({type: "svg"}).startsWith("data:image/svg"),
                apexNodes: document.querySelectorAll("[class*=apexcharts]").length,
                panEnabled: entry.panEnabled,
                legendTypes: echartsCharts.map((candidate) =>
                  candidate.chart.getOption().legend[0].type
                ),
                legendShows: echartsCharts.map((candidate) =>
                  candidate.chart.getOption().legend[0].show
                ),
                legendPanels: echartsCharts.map((candidate) => ({
                  clientHeight: candidate.legendPanel.clientHeight,
                  scrollHeight: candidate.legendPanel.scrollHeight,
                  overflowY: getComputedStyle(candidate.legendPanel).overflowY,
                  buttons: candidate.legendPanel.querySelectorAll(".chart-legend-item").length,
                })),
                chartHeights: echartsCharts.map((candidate) => candidate.container.clientHeight),
                stacks: echartsCharts.map((candidate) =>
                  candidate.chart.getOption().series.map((series) => series.stack || "")
                ),
                title: entry.chart.getOption().title[0].text,
                exportIcon: entry.chart.getOption().toolbox[0].feature.myExport.icon,
                formatSamples: {
                  axisCount: formatChartAxisValue(
                    140000, "count/s", {factor: 1000, label: "kcount/s"}
                  ),
                  tooltipCount: formatChartTooltipValue(
                    140000, "count/s", {factor: 1000, label: "kcount/s"}
                  ),
                  axisBytes: formatChartAxisValue(
                    19162.5, "bytes/s", {factor: 1024, label: "KiB/s"}
                  ),
                  tooltipBytes: formatChartTooltipValue(
                    19162.5, "bytes/s", {factor: 1024, label: "KiB/s"}
                  ),
                },
              };
            }"""
        )

        first_chart = page.locator(".echarts-chart").first
        first_chart.scroll_into_view_if_needed()
        chart_box = first_chart.bounding_box()
        assert chart_box is not None
        drag_y = chart_box["y"] + min(180, chart_box["height"] * 0.45)
        drag_start_x = chart_box["x"] + chart_box["width"] * 0.55
        page.mouse.move(drag_start_x, drag_y)
        page.mouse.down()
        page.mouse.move(drag_start_x - 120, drag_y, steps=8)
        page.mouse.up()
        page.wait_for_timeout(100)
        panned_zoom = page.evaluate("echartsCharts[0].zoomRange")

        crowded_legend_button = page.locator(".chart-legend-panel").nth(2).locator(
            ".chart-legend-item"
        ).first
        crowded_legend_button.click()
        assert crowded_legend_button.get_attribute("aria-pressed") == "false"
        crowded_legend_button.click()
        assert crowded_legend_button.get_attribute("aria-pressed") == "true"

        assert page.locator("html").get_attribute("data-theme") == "dark"
        page.evaluate("toggleEChartsExportMenu(echartsCharts[0])")
        export_menu = page.locator(".chart-export-menu").first
        assert export_menu.locator("button").all_inner_texts() == [
            "Export SVG",
            "Export PNG",
            "Export CSV",
        ]
        with page.expect_download() as svg_download_info:
            export_menu.locator('[data-export-format="svg"]').click()
        svg_download = svg_download_info.value
        svg_path = svg_download.path()
        assert svg_path is not None
        svg_text = svg_path.read_text(encoding="utf-8")

        page.evaluate("toggleEChartsExportMenu(echartsCharts[0])")
        with page.expect_download() as png_download_info:
            export_menu.locator('[data-export-format="png"]').click()
        png_download = png_download_info.value
        png_path = png_download.path()
        assert png_path is not None

        page.evaluate("toggleEChartsExportMenu(echartsCharts[0])")
        with page.expect_download() as csv_download_info:
            export_menu.locator('[data-export-format="csv"]').click()
        csv_download = csv_download_info.value

        page.locator("#themeToggle").check()
        page.wait_for_timeout(250)
        page.evaluate(
            'echartsCharts[0].chart.dispatchAction({type: "showTip", seriesIndex: 0, dataIndex: 1})'
        )
        tooltip = page.locator(".pg-diag-echarts-tooltip").first
        assert state["ready"] == 3
        assert state["svgs"] == 3
        assert state["renderer"] == "svg"
        assert state["zoom"] == {"start": 10, "end": 90}
        assert state["svgDataUrl"] is True
        assert state["apexNodes"] == 0
        assert state["panEnabled"] is True
        assert state["legendTypes"] == ["plain", "plain", "plain"]
        assert state["legendShows"] == [False, False, False]
        assert state["legendPanels"][0]["scrollHeight"] <= state["legendPanels"][0]["clientHeight"]
        assert state["legendPanels"][2]["scrollHeight"] > state["legendPanels"][2]["clientHeight"]
        assert state["legendPanels"][2]["overflowY"] == "auto"
        assert state["legendPanels"][2]["buttons"] == 30
        assert len(set(state["chartHeights"])) == 1
        assert state["chartHeights"][0] >= 468
        assert state["stacks"][0] == [""]
        assert state["stacks"][1] == ["pg_diag_stack", "pg_diag_stack"]
        assert state["stacks"][2] == ["pg_diag_stack"] * 30
        assert state["title"] == "Line [kcount/s]"
        assert state["exportIcon"] == "path://M2 8h7V2h6v6h7L12 20z"
        assert state["formatSamples"] == {
            "axisCount": "140",
            "tooltipCount": "140 kcount/s",
            "axisBytes": "18.713",
            "tooltipBytes": "18.713 KiB/s",
        }
        assert panned_zoom["start"] > state["zoom"]["start"] + 3
        assert panned_zoom["end"] > state["zoom"]["end"] + 3
        assert panned_zoom["end"] - panned_zoom["start"] == pytest.approx(80)
        assert svg_download.suggested_filename == "charts.line.svg"
        assert "<svg" in svg_text
        assert "#21182f" in svg_text.lower()
        assert png_download.suggested_filename == "charts.line.png"
        assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert csv_download.suggested_filename == "charts.line.csv"
        assert page.locator("html").get_attribute("data-theme") == "light"
        assert tooltip.locator(".pg-diag-chart-tooltip-row").count() == 1
        assert "select count(*)" in tooltip.inner_text()
        assert "140 kcount/s" in tooltip.inner_text()
        assert "140,000" not in tooltip.inner_text()
        assert external_requests == []
        assert errors == []
        browser.close()


def test_strip_meta_removes_item_action_buttons_in_browser(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    first_item = artifact["items"]["charts.line"]
    first_item["source_metadata"].update(
        {
            "source_text": "select private_check_source()",
            "source_language": "sql",
            "instructions": {
                "format": "markdown",
                "path": "instructions/items/charts/line.md",
                "text": "Private instruction",
            },
        }
    )
    strip_artifact_metadata(artifact)
    report_path = tmp_path / "stripped-report.html"
    report_path.write_text(render_html(artifact, validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.goto(report_path.as_uri(), wait_until="load")
        page.wait_for_function(
            "document.querySelectorAll('[data-chart-ready=true]').length === 3"
        )

        assert page.locator(".item-action-buttons button").count() == 0
        assert page.get_by_role("button", name="Show SQL").count() == 0
        assert page.get_by_role("button", name="Show Instruction").count() == 0
        assert page.get_by_role("button", name="Show meta").count() == 0
        assert page.locator(".item-tag").count() > 0
        assert page.evaluate("artifact.runtime.strip_meta") is True
        assert page.evaluate("artifact.content.document.queries") == {}
        browser.close()
