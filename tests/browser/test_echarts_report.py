from __future__ import annotations

import json
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
        "charts.line": _chart_result("line", [[120_000, 140_000, 130_000]], names=["query.123"]),
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
        "generator": {"name": "pg_diag", "version": "0.9.1"},
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
                "fallback_items": {},
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


def test_explain_available_button_ignores_axis_points_and_opens_filtered_item(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    item_id = "server_log.auto_explain_plans"
    cases = [
        ("missing", None, False),
        ("no-result", None, False),
        ("empty", [], False),
        ("axis-only", [{"t": "2026-07-15T10:00:00Z", "value": 0}], False),
        ("null-only", [{"t": "2026-07-15T10:00:00Z", "value": None}], False),
        ("plan", [{"t": "2026-07-15T10:00:00Z", "value": 25}], True),
        ("zero-duration-plan", [{"t": "2026-07-15T10:00:00Z", "value": 0,
                                  "tooltip": {"duration_ms": 0}}], True),
    ]
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        for name, points, available in cases:
            artifact = _artifact()
            if name != "missing":
                item = dict(artifact["items"]["charts.line"], item_id=item_id,
                            section_id="server_log", item_key="auto_explain_plans",
                            title="Auto explain plans", state="collapsed")
                item["result"] = None if points is None else {
                    "kind": "chart", "chart": {"kind": "stacked_column", "x_type": "datetime"},
                    "series": [{"name": "Rank 1", "points": points}],
                }
                artifact["items"][item_id] = item
                artifact["sections"].append({"section_id": "server_log", "title": "Server log",
                                             "state": "collapsed", "items": [item_id]})
            report = tmp_path / (name + ".html")
            report.write_text(render_html(artifact, validate=False), encoding="utf-8")
            page.goto(report.as_uri(), wait_until="load")
            button = page.locator("#explainAvailable")
            assert button.is_visible() is available, name
            if not available:
                continue
            target = page.locator(f'details.item[data-item-id="{item_id}"]')
            for theme, width in [("dark", 1440), ("light", 390)]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                page.locator("#itemSearch").fill("no-matching-explain-item")
                page.wait_for_function("id => findItemElement(id).classList.contains('hidden')", arg=item_id)
                button.click()
                page.wait_for_function("""id => {
                  const item = findItemElement(id);
                  return item.open && item.closest('details.section').open
                    && !item.closest('.hidden') && document.activeElement === directSummary(item);
                }""", arg=item_id)
                assert page.locator("#itemSearch").input_value() == ""
                summary_box = target.locator(":scope > summary").bounding_box()
                assert summary_box and 0 <= summary_box["y"] < 1000
        assert not errors
        browser.close()


@pytest.mark.parametrize("tooltip_kind", ["query_event", "log_event"])
def test_log_chart_dates_and_event_bounds(tmp_path: Path, tooltip_kind: str) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    result = artifact["items"]["charts.line"]["result"]
    result["chart"]["tooltip_kind"] = tooltip_kind
    result["series"] = [{"name": "Events", "points": [
        {"t": "2026-07-14T00:00:00Z", "value": 0},
        {"t": "2026-07-15T10:00:00Z", "value": 10},
        {"t": "2026-07-16T10:00:00Z", "value": 0, "tooltip": {"duration_ms": 0}},
        {"t": "2026-07-17T00:00:00Z", "value": None},
        {"t": "2026-07-18T00:00:00Z", "value": 0},
    ]}]
    report = tmp_path / "log-dates.html"
    report.write_text(render_html(artifact, validate=False), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(timezone_id="Europe/Moscow")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report.as_uri(), wait_until="load")
        page.wait_for_function("echartsCharts.length === 3")
        actual = page.evaluate("""() => {
          const entry = echartsCharts.find(e => e.item.item_id === 'charts.line');
          const axis = entry.chart.getOption().xAxis[0];
          const first = Date.parse('2026-07-15T10:00:00Z');
          const last = Date.parse('2026-07-16T10:00:00Z');
          const result = entry.result;
          const zeroOnly = {...result, series: [{name: 'Zero', points: [
            {t: '2026-07-15T10:00:00Z', value: 0, tooltip: {duration_ms: 0}}
          ]}]};
          return {
            lowerPadding: first - axis.min, upperPadding: axis.max - last,
            label: axis.axisLabel.formatter(first),
            pointer: axis.axisPointer.label.formatter({value: first}),
            values: entry.series[0].data.map(p => p.y),
            zeroCount: echartsSeries(zeroOnly).length,
            originalPoints: result.series[0].points.length,
            nonLogLabel: echartsCharts.find(e => e.item.item_id === 'charts.area')
              .chart.getOption().xAxis[0].axisLabel.formatter(first),
          };
        }""")
        assert actual == {
            "lowerPadding": 30000, "upperPadding": 30000,
            "label": "2026-07-15\n13:00:00", "pointer": "2026-07-15 13:00:00",
            "values": [10, 0], "zeroCount": 1, "originalPoints": 5,
            "nonLogLabel": "13:00:00",
        }
        assert not errors
        browser.close()


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
        page.wait_for_function("document.querySelectorAll('[data-chart-ready=true]').length === 3")
        state = page.evaluate(
            """() => {
              const entry = echartsCharts[0];
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

        crowded_legend_button = (
            page.locator(".chart-legend-panel").nth(2).locator(".chart-legend-item").first
        )
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
        page.locator("#reportTitle").click()
        assert export_menu.is_hidden()
        page.evaluate("toggleEChartsExportMenu(echartsCharts[0])")
        page.keyboard.press("Escape")
        assert export_menu.is_hidden()
        page.evaluate("toggleEChartsExportMenu(echartsCharts[0])")
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


def test_dense_legacy_auto_explain_bounds_do_not_overflow_stack(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    report_path = tmp_path / "dense-log-chart.html"
    report_path.write_text(render_html(_artifact(), validate=False), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(report_path.as_uri(), wait_until="load")
        result = page.evaluate(
            """() => {
              const base = Date.parse('2026-09-29T00:00:00Z');
              const point = (i) => ({t: new Date(base + i * 60000).toISOString(),
                value: 10000, tooltip: {duration_ms: 10000}});
              const result = {chart: {kind: 'stacked_column', x_type: 'datetime',
                tooltip_kind: 'query_event', unit: 'milliseconds'},
                series: Array.from({length: 250}, (_, i) => ({name: 'Rank ' + i,
                  points: i === 0 ? Array.from({length: 1751}, (_, j) => point(j))
                    : [point(0)]}))};
              const series = echartsSeries(result);
              const bounds = chartDatetimeBounds(series, true);
              return {alignedPoints: series.reduce((n, s) => n + s.data.length, 0),
                minOffset: bounds.min - base, maxOffset: bounds.max - base};
            }"""
        )
        assert result == {
            "alignedPoints": 437750,
            "minOffset": -30000,
            "maxOffset": 1750 * 60000 + 30000,
        }
        browser.close()


def test_query_event_chart_hides_legend_and_uses_point_tooltip(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    result = artifact["items"]["charts.line"]["result"]
    result["chart"].update(
        {
            "kind": "stacked_column",
            "show_legend": False,
            "tooltip_kind": "query_event",
            "unit": "milliseconds",
        }
    )
    nested_plan = {
        "Node Type": "Index Scan",
        "Index Name": "pg_description_o_c_o_index",
        "Relation Name": "pg_description",
        "Alias": "pgd",
        "Startup Cost": 0.01,
        "Total Cost": 1.0,
        "Plan Rows": 1,
        "Plan Width": 4,
        "Actual Startup Time": 0.001,
        "Actual Total Time": 0.002,
        "Actual Rows": 1,
        "Actual Loops": 1,
        "Shared Hit Blocks": 10,
    }
    for _ in range(18):
        nested_plan = {
            "Node Type": "Nested Loop Left Join",
            "Startup Cost": 0.01,
            "Total Cost": 1.0,
            "Plan Rows": 1,
            "Plan Width": 4,
            "Actual Startup Time": 0.001,
            "Actual Total Time": 0.002,
            "Actual Rows": 1,
            "Actual Loops": 1,
            "Shared Hit Blocks": 10,
            "Plans": [nested_plan],
        }
    viewer_plan = "duration: 12345.678 ms  plan:\n" + json.dumps(
        [
            {
                "Plan": nested_plan,
                "Query Text": "select 1",
                "Planning Time": 0.1,
                "Execution Time": 0.02,
            }
        ]
    )
    result["references"] = {
        "messages": {"m1": "canceling statement due to statement timeout"},
        "queries": {"q1": "select <unsafe> & escaped..."},
        "plans": {"p1": {"format": "json", "text": viewer_plan}},
    }
    for index, point in enumerate(result["series"][0]["points"]):
        point.update(
            {
                "value": 12_345.678,
                "color": "#f87171",
                "tooltip": {
                    "log_time": f"2026-07-15T10:00:{index * 5:02d}Z",
                    "duration_ms": 12_345.678,
                    "message_ref": "m1",
                    "query_ref": "q1",
                },
                "viewer": {
                    "plan_ref": "p1",
                    "read_only": True,
                },
            }
        )
    report_path = tmp_path / "query-event-chart.html"
    report_path.write_text(render_html(artifact, validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))

        page.goto(report_path.as_uri(), wait_until="load")
        page.wait_for_function("document.querySelectorAll('[data-chart-ready=true]').length === 3")
        state = page.evaluate(
            """() => ({
              legendPanel: echartsCharts[0].legendPanel,
              legendPanels: document.querySelectorAll(".chart-legend-panel").length,
              trigger: echartsCharts[0].chart.getOption().tooltip[0].trigger,
              pointColor: echartsCharts[0].chart.getOption().series[0].data[1].itemStyle.color,
            })"""
        )
        page.evaluate(
            'echartsCharts[0].chart.dispatchAction({type: "showTip", seriesIndex: 0, dataIndex: 1})'
        )
        tooltip = page.locator(".pg-diag-echarts-tooltip").first
        tooltip_text = tooltip.inner_text()
        click_hint = tooltip.locator(".pg-diag-chart-tooltip-action")

        assert state == {
            "legendPanel": None,
            "legendPanels": 2,
            "trigger": "item",
            "pointColor": "#f87171",
        }
        assert "2026-07-15T10:00:05Z" in tooltip_text
        assert "12.346 s" in tooltip_text
        duration_display = page.evaluate(
            """() => {
              const entry = echartsCharts[0];
              const options = buildEChartsOptions(entry);
              const sample = (value) => [{data: [{x: 'a', y: value}]}];
              const stacked = chartAxisScale(
                [...sample(600), ...sample(600)], 'milliseconds', null, true);
              const unstacked = chartAxisScale(
                [...sample(600), ...sample(600)], 'milliseconds', null, false);
              entry.chart.dispatchAction({type: 'dataZoom', start: 20, end: 80});
              const zoomed = buildEChartsOptions(entry);
              const exported = buildEChartsOptions(entry, null, true);
              return {
                title: options.title.text,
                axis: options.yAxis.axisLabel.formatter(12000),
                zoomedAxis: zoomed.yAxis.axisLabel.formatter(12000),
                exportedAxis: exported.yAxis.axisLabel.formatter(12000),
                stacked, unstacked,
                boundary: chartAxisScale(sample(1000), 'ms', null, false),
                belowBoundary: chartAxisScale(sample(999), 'ms', null, false),
                durations: [256961.866, 999.123, 1000, 0].map(formatDurationMilliseconds),
                stackedTooltip: formatChartTooltipValue(600, 'milliseconds', stacked),
              };
            }"""
        )
        assert duration_display == {
            "title": "Line [s]",
            "axis": "12",
            "zoomedAxis": "12",
            "exportedAxis": "12",
            "stacked": {"factor": 1000, "label": "s"},
            "unstacked": {"factor": 1, "label": "ms"},
            "boundary": {"factor": 1000, "label": "s"},
            "belowBoundary": {"factor": 1, "label": "ms"},
            "durations": ["256.962 s", "999.123 ms", "1 s", "0 ms"],
            "stackedTooltip": "0.6 s",
        }
        assert "select <unsafe> & escaped..." in tooltip_text
        assert click_hint.inner_text() == "Click to show explain"
        assert click_hint.evaluate("node => getComputedStyle(node).textAlign") == "center"
        assert click_hint.evaluate("node => Number(getComputedStyle(node).fontWeight)") >= 700
        assert (
            click_hint.evaluate("node => getComputedStyle(node).backgroundColor")
            != "rgba(0, 0, 0, 0)"
        )
        assert page.locator(".pg-diag-echarts-tooltip script").count() == 0
        page.evaluate(
            """() => openQueryPlanViewerFromChart({
              data: echartsCharts[0].chart.getOption().series[0].data[1],
            })"""
        )
        modal = page.locator("#planViewerModal")
        assert modal.is_visible()
        assert "Query plan (read-only) · JSON" in modal.inner_text()
        assert modal.locator("#planViewerRoot.pv").count() == 1
        assert modal.locator("textarea, input").count() == 0
        assert modal.get_by_text("Export", exact=True).count() == 0
        node_layout = modal.evaluate(
            """(modal) => {
              const wrap = modal.querySelector(".pv-tablewrap");
              const overlaps = [...modal.querySelectorAll("tr.pv-row")].map((row) => {
                const node = row.querySelector("td.pv-nodecell");
                const head = row.querySelector(".pv-nodehead");
                const next = node && node.nextElementSibling;
                if (!node || !head || !next) return null;
                return head.getBoundingClientRect().right - next.getBoundingClientRect().left;
              }).filter((value) => value !== null);
              return {
                measuredRows: overlaps.length,
                maxOverlap: Math.max(...overlaps),
                scrollsHorizontally: wrap.scrollWidth > wrap.clientWidth,
              };
            }"""
        )
        assert node_layout["measuredRows"] > 0
        assert node_layout["maxOverlap"] <= 0
        assert node_layout["scrollsHorizontally"] is True
        dialog = modal.locator(".plan-viewer-dialog")
        shell = modal.locator("#planViewerShell")
        dialog_before_tab = dialog.bounding_box()
        assert dialog_before_tab is not None
        assert dialog_before_tab["y"] == pytest.approx(24, abs=1)
        assert dialog_before_tab["y"] + dialog_before_tab["height"] <= 900 - 23
        modal.get_by_role("tab", name="Plan text", exact=True).click()
        dialog_after_tab = dialog.bounding_box()
        assert dialog_after_tab is not None
        assert dialog_after_tab["y"] == pytest.approx(dialog_before_tab["y"], abs=1)
        background_scroll = page.evaluate("window.scrollY")
        page.evaluate(
            """() => {
              const spacer = document.createElement("div");
              spacer.id = "planViewerOverflowProbe";
              spacer.style.height = "1400px";
              document.getElementById("planViewerRoot").appendChild(spacer);
            }"""
        )
        assert shell.evaluate("node => node.scrollHeight > node.clientHeight")
        shell.evaluate("node => { node.scrollTop = 120; }")
        assert shell.evaluate("node => node.scrollTop") == pytest.approx(120, abs=1)
        assert page.evaluate("window.scrollY") == background_scroll
        page.evaluate('setTheme("light", false)')
        assert page.locator("html").get_attribute("data-pv-theme") == "light"
        assert (
            modal.locator("#planViewerRoot").evaluate(
                "node => getComputedStyle(node).backgroundColor"
            )
            == "rgb(255, 255, 255)"
        )
        modal.get_by_role("button", name="Close").click()
        assert modal.is_hidden()
        assert errors == []
        browser.close()


def test_log_event_chart_resolves_deduplicated_message_and_query_refs(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    result = artifact["items"]["charts.line"]["result"]
    result["chart"].update(
        {
            "kind": "stacked_column",
            "show_legend": False,
            "tooltip_kind": "log_event",
        }
    )
    result["references"] = {
        "messages": {"m1": "canceling statement due to statement timeout"},
        "queries": {"q1": "select * from orders where id = 42"},
    }
    result["series"][0]["points"][1].update(
        {
            "value": 3,
            "tooltip": {
                "log_time": "2026-07-15T10:00:05Z",
                "event_type": "statement_timeout",
                "occurrences": 3,
                "sql_state": "57014",
                "message_ref": "m1",
                "query_ref": "q1",
            },
        }
    )
    report_path = tmp_path / "log-event-chart.html"
    report_path.write_text(render_html(artifact, validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report_path.as_uri(), wait_until="load")
        page.wait_for_function("document.querySelectorAll('[data-chart-ready=true]').length === 3")
        page.evaluate(
            'echartsCharts[0].chart.dispatchAction({type: "showTip", seriesIndex: 0, dataIndex: 1})'
        )

        tooltip_text = page.locator(".pg-diag-echarts-tooltip").first.inner_text()
        assert "statement_timeout" in tooltip_text
        assert "57014" in tooltip_text
        assert "3" in tooltip_text
        assert "select * from orders where id = 42" in tooltip_text
        assert "canceling statement due to statement timeout" in tooltip_text
        assert errors == []
        browser.close()


def test_filter_resizes_chart_initialized_inside_collapsed_section(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    artifact["sections"][0]["state"] = "collapsed"
    report_path = tmp_path / "filtered-chart-report.html"
    report_path.write_text(render_html(artifact, validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))

        page.goto(report_path.as_uri(), wait_until="load")
        page.wait_for_function("document.querySelectorAll('[data-chart-ready=true]').length === 3")
        page.locator("#itemSearch").fill("charts.columns")
        page.wait_for_function(
            """() => {
              const entry = echartsCharts.find(
                (candidate) => candidate.item.item_id === "charts.columns"
              );
              const section = document.querySelector(
                'details.section[data-section-id="charts"]'
              );
              return Boolean(
                entry
                && section
                && section.open
                && entry.container.clientWidth > 640
                && Math.abs(entry.chart.getWidth() - entry.container.clientWidth) <= 1
              );
            }"""
        )
        layout = page.evaluate(
            """() => {
              const entry = echartsCharts.find(
                (candidate) => candidate.item.item_id === "charts.columns"
              );
              const svg = entry.container.querySelector("svg");
              return {
                containerWidth: entry.container.clientWidth,
                chartWidth: entry.chart.getWidth(),
                svgWidth: Number(svg && svg.getAttribute("width")),
              };
            }"""
        )

        assert layout["containerWidth"] > 640
        assert layout["chartWidth"] == pytest.approx(layout["containerWidth"], abs=1)
        assert layout["svgWidth"] == pytest.approx(layout["containerWidth"], abs=1)
        assert errors == []
        browser.close()


def test_single_cell_numeric_table_aligns_value_left_in_browser(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    artifact["content"]["document"]["sections"]["charts"]["items"]["total_ram"] = {
        "metric": "test.total_ram",
        "tags": ["Memory", "Hardware"],
    }
    artifact["items"]["charts.total_ram"] = {
        "item_id": "charts.total_ram",
        "section_id": "charts",
        "item_key": "total_ram",
        "title": "Total RAM Capacity",
        "source_kind": "metric",
        "collection_scope": "once",
        "collection_status": "ok",
        "severity_level": "ok",
        "state": "expanded",
        "result": {
            "kind": "table",
            "columns": [
                {
                    "name": "total_ram_bytes",
                    "label": "Total RAM bytes",
                    "pg_type": "int8",
                    "value_kind": "integer",
                    "semantic_role": "gauge",
                    "quantity": "data_volume",
                    "unit": "bytes",
                    "quality": "exact",
                    "nullable": False,
                    "encoding": "decimal_string",
                }
            ],
            "rows": [["105473638400"]],
        },
        "source_metadata": {
            "metric_id": "test.total_ram",
            "tags": ["Memory", "Hardware"],
        },
        "diagnostics": [],
        "issues": {},
    }
    artifact["sections"][0]["items"].append("charts.total_ram")
    report_path = tmp_path / "single-cell-table-report.html"
    report_path.write_text(render_html(artifact, validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report_path.as_uri(), wait_until="load")

        table = page.locator(
            'details.item[data-item-id="charts.total_ram"] table.single-cell-table'
        )
        cell = table.locator("tbody td")
        assert table.count() == 1
        assert cell.count() == 1
        assert cell.evaluate("element => getComputedStyle(element).textAlign") == "left"
        assert errors == []
        browser.close()


def test_fallback_raw_metadata_uses_effective_cross_kind_source(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    document = artifact["content"]["document"]
    document["defaults"].update(
        {
            "item": {"state": "collapsed", "database_scope": "all_databases"},
            "section": {"state": "expanded"},
        }
    )
    document["field_reference"] = {
        **{
            root: f"{root} test metadata."
            for root in (
                "runtime_policy",
                "defaults",
                "sections",
                "fallback_items",
                "python_sources",
                "instructions",
                "resolved",
            )
        },
        **{"/".join(["*"] * depth): "Nested test metadata." for depth in range(2, 9)},
    }
    document["sections"]["charts"]["items"]["fallback"] = {
        "query": "primary.query",
        "fallback_item": "fallback.charts.python",
        "fallback_on": ["statement_timeout"],
        "tags": ["Tables"],
    }
    document["queries"]["primary.query"] = {
        "title": "Primary Query",
        "variants": [
            {
                "id": "primary_query_pg14_plus",
                "min_pg_version": 140000,
                "sql_file": "primary/query.sql",
            }
        ],
    }
    document["python_sources"]["fallback.python"] = {
        "title": "Fallback Python",
        "python_file": "python/fallback.py",
        "function": "collect",
    }
    document["fallback_items"]["fallback.charts.python"] = {
        "title": "Fallback Python",
        "python": "fallback.python",
        "instruction": "fallback_items/charts/python.md",
    }
    document["instructions"] = {
        "fallback.charts.python": {
            "format": "markdown",
            "path": "instructions/fallback_items/charts/python.md",
            "text": "# Fallback Python",
        }
    }
    artifact["content"]["provenance"].update(
        {
            "fallback_items/fallback.charts.python": ["report.yaml"],
            "python_sources/fallback.python": ["python.yaml"],
            "instructions/fallback.charts.python": ["instructions/fallback_items/charts/python.md"],
        }
    )
    artifact["items"]["charts.fallback"] = {
        "item_id": "charts.fallback",
        "section_id": "charts",
        "item_key": "fallback",
        "title": "[Fallback] Fallback Python",
        "source_kind": "python",
        "collection_scope": "once",
        "collection_status": "ok",
        "severity_level": "unknown",
        "state": "expanded",
        "result": {"kind": "plain_text", "data": "approximate evidence"},
        "source_metadata": {
            "python_id": "fallback.python",
            "python_file": "python/fallback.py",
            "function": "collect",
            "source_text": "def collect(context): return 'approximate evidence'",
            "source_language": "python",
            "tags": ["Tables"],
            "instructions": document["instructions"]["fallback.charts.python"],
            "fallback": {
                "used": True,
                "trigger": "statement_timeout",
                "parent_item_id": "charts.fallback",
                "fallback_item_id": "fallback.charts.python",
                "effective_item_id": "fallback.charts.python",
            },
        },
        "diagnostics": [],
        "issues": {},
    }
    artifact["sections"][0]["items"].append("charts.fallback")
    report_path = tmp_path / "fallback-raw-meta.html"
    report_path.write_text(render_html(artifact, validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(report_path.as_uri(), wait_until="load")

        fallback_item = page.locator('details.item[data-item-id="charts.fallback"]')
        fallback_item.get_by_role("button", name="Show meta").click()
        page.get_by_role("tab", name="Raw").click()
        raw = page.locator("#metaRawCode").inner_text()

        assert errors == []
        assert "fallback_items:" in raw
        assert "fallback.charts.python:" in raw
        assert "python_sources:" in raw
        assert "fallback.python:" in raw
        assert "python/fallback.py" in raw
        assert "instructions:" in raw
        assert "instructions/fallback_items/charts/python.md" in raw
        assert 'effective_item_id: "fallback.charts.python"' in raw
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
        page.wait_for_function("document.querySelectorAll('[data-chart-ready=true]').length === 3")

        assert page.locator(".item-action-buttons button").count() == 0
        assert page.get_by_role("button", name="Show SQL").count() == 0
        assert page.get_by_role("button", name="Show Instruction").count() == 0
        assert page.get_by_role("button", name="Show meta").count() == 0
        assert page.locator(".item-tag").count() > 0
        assert page.evaluate("artifact.runtime.strip_meta") is True
        assert page.evaluate("artifact.content.document.queries") == {}
        browser.close()


def test_instruction_item_links_expand_present_targets_and_disable_missing_targets(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    artifact["items"]["charts.line"]["source_metadata"]["instructions"] = {
        "format": "markdown",
        "path": "instructions/items/charts/line.md",
        "text": (
            "# Line\n\n## Related report items\n"
            "- [charts.columns](#item-charts.columns) — inspect columns.\n"
            "- [charts.missing](#item-charts.missing) — unavailable in this report."
        ),
    }
    artifact["items"]["charts.columns"]["state"] = "collapsed"
    report_path = tmp_path / "instruction-links-report.html"
    report_path.write_text(render_html(artifact, validate=False), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.goto(report_path.as_uri(), wait_until="load")
        page.locator('details.item[data-item-id="charts.line"]').evaluate(
            "element => { element.open = true; }"
        )
        page.locator('details.item[data-item-id="charts.line"]').get_by_role(
            "button", name="Show Instruction"
        ).click()

        active = page.locator('#instructionBody a[data-item-id="charts.columns"]')
        unavailable = page.locator("#instructionBody .report-item-link.unavailable")
        assert active.count() == 1
        assert unavailable.count() == 1
        assert unavailable.get_attribute("aria-disabled") == "true"
        assert unavailable.inner_text() == "charts.missing"

        page.locator('details.section[data-section-id="charts"]').evaluate(
            "element => { element.open = false; }"
        )
        page.locator('details.item[data-item-id="charts.columns"]').evaluate(
            "element => { element.open = false; }"
        )
        active.click()

        page.wait_for_function(
            """() => {
              const section = document.querySelector('details.section[data-section-id="charts"]');
              const item = document.querySelector('details.item[data-item-id="charts.columns"]');
              return section && section.open && item && item.open;
            }"""
        )
        assert page.locator("#instructionModal").is_hidden()
        assert page.url.endswith("#item-charts.columns")
        browser.close()


def test_log_tables_open_shared_query_texts_after_filtering_and_sorting(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    first = "SELECT first_variant"
    second = "SELECT second_variant " + "x" * 1978
    artifact["query_texts"] = {"log:a": first, "log:b": second}
    artifact["query_text_metadata"] = {"log:b": {"truncated": True, "max_chars": 2000}}
    artifact["items"]["charts.line"]["result"] = {
        "kind": "table",
        "columns": [{"name": "query_id", "pg_type": "json", "encoding": "json_value"},
                    {"name": "occurrences", "pg_type": "int8", "encoding": "decimal_string"}],
        "rows": [["0", "2"], ["0", "3"], [["0", "-7074349522848144440"], "4"]],
        "row_count": 3,
        "query_links": {"query_id": ["log:a", "log:b", ["log:a", "log:b"]]},
    }
    path = tmp_path / "log-query-links.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(path.as_uri(), wait_until="load")
        table = page.locator('[data-item-id="charts.line"]')
        table.locator(".query-id-button").first.hover()
        page.wait_for_timeout(200)
        assert "first_variant" in page.locator(".hover-preview").inner_text()
        table.locator(".query-id-button").nth(1).click()
        assert page.locator("#sourceCode").inner_text() == second
        assert "truncated to 2000 characters" in page.locator("#sourceModalTitle").inner_text()
        page.locator("#closeSource").click()
        table.locator('input[type="search"]').fill("second_variant")
        assert table.locator("tbody tr").count() == 2
        table.locator("th").nth(1).click()
        button = table.get_by_role("button", name="-7074349522848144440", exact=True)
        button.click()
        assert page.locator("#sourceCode").inner_text() == second
        assert errors == []
        browser.close()


def test_log_event_chart_opens_query_from_global_catalog(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    result = artifact["items"]["charts.line"]["result"]
    result["chart"].update(kind="stacked_column", tooltip_kind="log_event")
    artifact["query_texts"]["log:test"] = "SELECT chart_query"
    result["series"][0]["points"][1]["tooltip"] = {
        "query_ref": "log:test", "event_type": "statement_timeout", "occurrences": 1,
    }
    path = tmp_path / "global-log-event.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function("document.querySelectorAll('[data-chart-ready=true]').length === 3")
        page.evaluate('''() => {
            const entry = echartsCharts[0];
            const data = entry.chart.getOption().series[0].data[1];
            entry.chart.dispatchAction({type: "showTip", seriesIndex: 0, dataIndex: 1});
            entry.chart.trigger("click", {data});
        }''')
        assert page.locator("#sourceCode").inner_text() == "SELECT chart_query"
        assert page.locator("#sourceModal").is_visible()
        browser.close()


def test_log_query_ids_use_one_catalog_sample_and_show_generated_hash(tmp_path: Path) -> None:
    from pg_diag.logscan.query_links import query_reference

    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    native = "5582924868496553877"
    sql = "SELECT saved_sample"
    hashed_sql = "START_REPLICATION SLOT logical_slot LOGICAL 0/0"
    generated = query_reference(hashed_sql, 0)
    artifact["query_texts"] = {native: sql, generated: hashed_sql}
    artifact["query_text_metadata"] = {native: {"representative_sample": True}}
    artifact["items"]["charts.line"]["result"] = {
        "kind": "table",
        "columns": [{"name": "query_id", "pg_type": "text", "encoding": "string"}],
        "rows": [[native], [native], [generated]],
        "row_count": 3,
        # The second record has an ID but no own SQL: it reuses the catalog.
        "query_links": {"query_id": [native, None, generated]},
    }
    path = tmp_path / "stable-log-query-ids.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(path.as_uri(), wait_until="load")
        buttons = page.locator(".query-id-button")
        assert buttons.all_text_contents() == [native, native, generated]
        for index in (0, 1):
            buttons.nth(index).hover()
            page.wait_for_timeout(200)
            assert sql in page.locator(".hover-preview").inner_text()
            buttons.nth(index).click()
            assert page.locator("#sourceCode").inner_text() == sql
            assert "SQL sample for this Query ID" in page.locator("#sourceModalTitle").inner_text()
            page.locator("#closeSource").click()
        buttons.nth(2).click()
        assert page.locator("#sourceCode").inner_text() == hashed_sql
        assert generated in page.locator("#sourceModalTitle").inner_text()
        assert errors == []
        browser.close()


@pytest.mark.parametrize("storage_available", [True, False])
def test_sql_format_preference_applies_to_all_windows_and_preserves_catalog(
    tmp_path: Path, storage_available: bool,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    queries = {
        "11": "WITH payload_raw AS (SELECT j.item ->> 'key' AS value FROM jsonb_array_elements($1::jsonb) AS j(item)) SELECT value FROM payload_raw WHERE value IS NOT NULL",
        "22": "select a, count(*) from example where a > 1 group by a",
        "33": "SELECT 'unterminated",
    }
    artifact["query_texts"] = queries.copy()
    artifact["items"]["charts.line"]["result"] = {
        "kind": "table", "columns": [{"name": "query_id"}],
        "rows": [[key] for key in queries], "row_count": len(queries),
    }
    path = tmp_path / "format-sql.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        if not storage_available:
            page.add_init_script('''Object.defineProperty(window, "localStorage", {
                get() { throw new Error("storage blocked"); }
            });''')
        page.add_init_script('''Object.defineProperty(navigator, "clipboard", {
            value: {writeText: async (text) => { window.copiedSQL = text; }}
        });''')
        errors = []
        requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.goto(path.as_uri(), wait_until="load")
        checkbox = page.get_by_role("checkbox", name="Format", exact=True)
        code = page.locator("#sourceCode")
        page.get_by_role("button", name="11", exact=True).click()
        assert not checkbox.is_checked()
        assert code.inner_text() == queries["11"]
        checkbox.check()
        first_formatted = code.inner_text()
        assert "\n" in first_formatted
        assert page.locator("#formatSqlStatus").is_hidden()
        page.locator("#copySource").click()
        assert page.evaluate("window.copiedSQL") == first_formatted
        page.locator("#closeSource").click()
        page.get_by_role("button", name="22", exact=True).click()
        assert checkbox.is_checked()
        assert "\n" in code.inner_text()
        assert page.evaluate("artifact.query_texts") == queries
        page.locator("#closeSource").click()
        page.get_by_role("button", name="33", exact=True).click()
        assert checkbox.is_checked()
        assert code.inner_text() == queries["33"]
        assert page.locator("#formatSqlStatus").is_visible()
        assert code.evaluate("el => getComputedStyle(el).whiteSpace") == "pre-wrap"
        page.locator("#closeSource").click()
        page.get_by_role("button", name="11", exact=True).click()
        assert checkbox.is_checked()
        assert code.inner_text() == first_formatted
        assert page.locator("#formatSqlStatus").is_hidden()
        if storage_available:
            page.reload(wait_until="load")
            page.get_by_role("button", name="11", exact=True).click()
            assert checkbox.is_checked()
            assert code.inner_text() == first_formatted
        checkbox.uncheck()
        assert code.inner_text() == queries["11"]
        page.locator("#closeSource").click()
        page.get_by_role("button", name="22", exact=True).click()
        assert not checkbox.is_checked()
        assert code.inner_text() == queries["22"]
        assert page.evaluate("artifact.query_texts") == queries
        assert errors == []
        assert not [url for url in requests if url.startswith(("http:", "https:"))]
        browser.close()


@pytest.mark.parametrize("incomplete_source", [None, "row", "result", "coverage", "truncated"])
def test_log_count_columns_are_hidden_with_one_warning_and_json_preserved(
    tmp_path: Path, incomplete_source: str | None,
) -> None:
    from copy import deepcopy

    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    template = deepcopy(artifact["items"]["charts.line"])
    chart = deepcopy(template["result"])
    source_dir = Path(__file__).parents[2] / "src/pg_diag/content/python/server_log"
    source_ids = ["server_log." + path.stem for path in sorted(source_dir.glob("*.py"))]
    source_ids = [key for key in source_ids if not key.rsplit(".", 1)[1].startswith("_")]
    inventory_id = "server_log.log_files_overview"
    event_ids = [key for key in source_ids if key != inventory_id]
    artifact["query_texts"] = {"42": "SELECT retained_sql"}
    coverage = {"ranking_complete": incomplete_source != "coverage",
                "window_truncated": incomplete_source == "truncated"}
    artifact["runtime"]["log_collection"] = {"coverage": coverage}
    artifact["items"] = {}
    for item_id in source_ids + ["sql_workload.control"]:
        item = deepcopy(template)
        item.update(item_id=item_id, source_kind="python", title=item_id)
        # Intentionally omit source metadata to cover reports with stripped metadata.
        item["source_metadata"] = {}
        item["result"] = {
            "kind": "table",
            "columns": [{"name": "message"}, {"name": "count_complete", "label": "Count complete"}, {"name": "query_id"}],
            "rows": [["first", True, "42"], ["last", incomplete_source != "row", "42"]],
            "row_count": 2,
            "count_complete": incomplete_source != "result",
            # A presentation cap is distinct from incomplete collection.
            "omitted_event_count": 100,
        }
        artifact["items"][item_id] = item
    chart_id = "server_log.auto_explain_plans"
    # All tables must hide the column, but the chart also needs a coverage warning.
    artifact["items"][chart_id]["result"] = chart
    chart["count_complete"] = incomplete_source not in ("row", "result")
    empty_id = "server_log.archiver_failures"
    artifact["items"][empty_id]["result"]["rows"] = []
    artifact["items"][empty_id]["result"]["row_count"] = 0
    artifact["items"][empty_id]["result"]["count_complete"] = incomplete_source not in ("row", "result")
    artifact["items"][empty_id]["collection_status"] = "empty"
    artifact["sections"][0]["items"] = list(artifact["items"])
    expected_results = {key: deepcopy(item["result"]) for key, item in artifact["items"].items()}
    path = tmp_path / "log-completeness.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(path.as_uri(), wait_until="load")
        for item_id in event_ids:
            item = page.locator(f'details.item[data-item-id="{item_id}"]')
            assert "Count complete" not in item.locator("th").all_text_contents()
            assert item.locator(".log-count-warning").count() == int(incomplete_source is not None)
        for item_id in (inventory_id, "sql_workload.control"):
            item = page.locator(f'details.item[data-item-id="{item_id}"]')
            assert "Count complete" in item.locator("th").all_text_contents()
            assert item.locator(".log-count-warning").count() == 0
        item = page.locator('details.item[data-item-id="server_log.authentication_failures"]')
        item.get_by_role("button", name="42", exact=True).first.click()
        assert page.locator("#sourceCode").inner_text() == "SELECT retained_sql"
        page.locator("#closeSource").click()
        item.locator('input[type="search"]').fill("last")
        assert item.locator("tbody tr").count() == 1
        assert item.locator(".log-count-warning").count() == int(incomplete_source is not None)
        retained = page.evaluate("Object.fromEntries(Object.entries(artifact.items).map(([k,v]) => [k,v.result]))")
        assert retained == expected_results
        assert errors == []
        browser.close()


def test_replication_commands_render_in_full_without_query_links(tmp_path: Path) -> None:
    from copy import deepcopy

    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    item = artifact["items"].pop("charts.line")
    item_id = "server_log.replication_events"
    item["item_id"] = item_id
    artifact["items"][item_id] = item
    artifact["sections"][0]["items"] = [item_id if key == "charts.line" else key
                                         for key in artifact["sections"][0]["items"]]
    command = 'START_REPLICATION SLOT "logical_slot" LOGICAL 0/123\n' + '\n'.join(
        f"  /* publication option {i} */" for i in range(8)
    )
    other_command = "IDENTIFY_SYSTEM"
    artifact["query_texts"] = {"short_hash": command, "22": other_command}
    item["result"] = {
        "kind": "table", "columns": [{"name": "message"}, {"name": "query_id", "label": "Query id"}],
        "rows": [["timeout", "11"], ["context", "22"], ["no saved SQL", "33"]], "row_count": 3,
        "query_links": {"query_id": ["short_hash", None, None]},
    }
    original = deepcopy(item["result"])
    path = tmp_path / "replication-commands.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(path.as_uri(), wait_until="load")
        item_node = page.locator(f'details.item[data-item-id="{item_id}"]')
        headers = item_node.locator("th").all_text_contents()
        assert "Replication command" in headers and "Query id" not in headers
        assert item_node.locator(".query-id-button, a, .cell-toggle").count() == 0
        assert item_node.locator("tbody tr").first.locator("td").nth(1).inner_text() == command
        assert item_node.locator("tbody tr").first.locator("td .cell-content").nth(1).get_attribute("class").endswith("expanded")
        assert item_node.locator("tbody tr").nth(2).locator("td").nth(1).inner_text() == ""
        item_node.get_by_role("button", name="Replication command", exact=True).click()
        assert item_node.locator("tbody tr").first.locator("td").nth(1).inner_text() == other_command
        for raw in (False, True):
            exported = page.evaluate('(raw) => tableExportData(tableViews.find(s => s.item.item_id === "server_log.replication_events"), raw)', raw)
            assert exported["header"] == ["message", "Replication command"]
            assert exported["rows"] == [["context", other_command], ["timeout", command], ["no saved SQL", ""]]
        item_node.locator('input[type="search"]').fill("publication option 7")
        assert item_node.locator("tbody tr").count() == 1
        assert page.evaluate('(id) => artifact.items[id].result', item_id) == original
        assert page.evaluate('artifact.query_texts.short_hash') == command
        assert errors == []
        browser.close()


def test_log_column_order_preserves_query_links_sorting_and_exports(tmp_path: Path) -> None:
    from copy import deepcopy

    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = _artifact()
    template = deepcopy(artifact["items"]["charts.line"])
    expected = {
        "server_log.error_chronology": ["first_time", "severity", "query_id"],
        "server_log.top_errors": ["occurrences", "sql_state", "query_id"],
        "server_log.query_resource_events": ["event_type", "total_temp_bytes", "max_duration_ms", "query_id"],
        "server_log.lock_waits": ["first_time", "wait_ms", "query_id"],
    }
    names = ["message", "occurrences", "first_time", "severity", "sql_state", "database_name",
             "event_type", "max_duration_ms", "total_temp_bytes", "wait_ms", "query_id", "count_complete"]
    rows = [["first", 1, "2026-09-29 10:00:00", "ERROR", "40P01", "db", "temporary_file", 100, 1000, 30, "11", True],
            ["second", 2, "2026-09-29 11:00:00", "ERROR", "40P01", "db", "temporary_file", 200, 2000, 60, "22", True]]
    artifact["query_texts"] = {"11": "SELECT first_sql", "22": "SELECT second_sql"}
    artifact["items"] = {}
    for key in list(expected) + ["sql_workload.control"]:
        item = deepcopy(template)
        item.update(item_id=key, source_kind="python", source_metadata={})
        item["result"] = {
            "kind": "table", "columns": [{"name": name} for name in names],
            "rows": deepcopy(rows), "row_count": 2,
            "query_links": {"query_id": ["11", "22"]},
        }
        artifact["items"][key] = item
    artifact["sections"][0]["items"] = list(artifact["items"])
    original = deepcopy(artifact["items"])
    path = tmp_path / "log-column-order.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(path.as_uri(), wait_until="load")
        for key, leading in expected.items():
            item = page.locator(f'details.item[data-item-id="{key}"]')
            assert item.locator("th").all_text_contents()[:len(leading)] == leading
            item.get_by_role("button", name="occurrences", exact=True).click()
            item.get_by_role("button", name="occurrences", exact=True).click()
            item.locator(".query-id-button").first.click()
            assert page.locator("#sourceCode").inner_text() == "SELECT second_sql"
            page.locator("#closeSource").click()
            item.locator('input[type="search"]').fill("first_sql")
            assert item.locator("tbody tr").count() == 1
            item.locator(".query-id-button").first.click()
            assert page.locator("#sourceCode").inner_text() == "SELECT first_sql"
            page.locator("#closeSource").click()
            exported = page.evaluate('(id) => tableExportData(tableViews.find(s => s.item.item_id === id), true)', key)
            assert exported["header"][:len(leading)] == leading
            assert exported["rows"][0][exported["header"].index("query_id")] == "11"
            assert exported["rows"][0][exported["header"].index("message")] == "first"
        assert page.locator('details.item[data-item-id="sql_workload.control"] th').all_text_contents() == names
        assert page.evaluate('Object.fromEntries(Object.entries(artifact.items).map(([k,v]) => [k,v.result]))') == {
            key: item["result"] for key, item in original.items()
        }
        # All item profiles retain source indexes and a visible query position,
        # even when optional fields are absent or new fields are appended.
        assert page.evaluate('''() => Object.keys(LOG_TABLE_COLUMN_ORDER).every(item_id => {
            const names = LOG_TABLE_COLUMN_ORDER[item_id];
            return [names, ["extra_a", "query_id", "extra_b", "extra_c"]].every(fields => {
                const columns = fields.map((name, sourceIndex) => ({name, sourceIndex}));
                const ordered = orderLogTableColumns(columns, {item_id});
                const pos = ordered.findIndex(c => c.name === "query_id");
                return pos >= 2 && pos <= 6 && ordered.length === columns.length
                  && ordered.every(c => columns[c.sourceIndex] === c);
            });
        })''')
        assert errors == []
        browser.close()
