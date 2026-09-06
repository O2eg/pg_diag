"""Offline integration of the real configurator UI with report-derived inputs."""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

import pytest

from pg_diag.render.html import render_html
from test_echarts_report import _artifact

pytestmark = pytest.mark.skipif(
    os.environ.get("PG_DIAG_BROWSER_TESTS") != "1", reason="set PG_DIAG_BROWSER_TESTS=1"
)


def configurator_artifact():
    artifact = _artifact()
    artifact["runtime"].update(server_version_num=180004, server_version="PostgreSQL 18.4 on Linux")
    def table(columns, rows):
        return {"kind": "table", "columns": [{"name": c} for c in columns], "rows": rows}
    data = {
        "os.cpu_info": {"kind": "plain_text", "data": "CPU(s): 8\n"},
        "os.total_ram": table(["total_ram_bytes"], [[str(16 * 1024**3)]]),
        "os.lshw_disk": table(["logicalname", "description"], [["/dev/nvme0n1", "NVMe disk"]]),
        "overview.pg_settings": table(["setting_name", "setting_value", "source_unit"], [
            ["max_connections", "100", None], ["shared_buffers", "1024", "8kB"],
            ["custom.extension", ' line1,"quote"\n</script><script>window.injected=true</script> ', None],
            ["synchronous_standby_names", "", None],
            ["wal_level", "replica", None], ["archive_mode", "off", None],
        ]),
    }
    base = artifact["items"]["charts.line"]
    for item_id, result in data.items():
        artifact["items"][item_id] = {**base, "item_id": item_id, "item_key": item_id,
                                      "title": item_id, "result": result}
        artifact["sections"][0]["items"].append(item_id)
    return artifact


def test_configurator_offline_diff_recalculation_theme_and_close(tmp_path: Path):
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = configurator_artifact()
    path = tmp_path / "report.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(offline=True, viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors, external = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: external.append(r.url) if r.url.startswith(("http:", "https:")) else None)
        page.goto(path.as_uri())
        assert page.locator("#showConfigurator").is_visible()
        assert not page.locator("#explainAvailable").is_visible()
        page.locator("#showConfigurator").click()
        frame = page.frame_locator("#configuratorFrame")
        frame.locator("#diff-summary").wait_for()
        assert "6 settings" in frame.locator("#diff-summary").inner_text()
        parsed = list(csv.DictReader(io.StringIO(frame.locator("#diff-input").input_value())))
        assert len(parsed) == 6
        assert parsed[1]["unit"] == "8kB"
        assert parsed[2]["setting"] == artifact["items"]["overview.pg_settings"]["result"]["rows"][2][1]
        assert frame.locator("#diff-results tbody tr").count() > 0
        shared_buffers = frame.locator("#diff-results tbody tr").filter(
            has=frame.get_by_text("shared_buffers", exact=True)
        )
        assert shared_buffers.locator("td").nth(2).inner_text() == "8192kB"
        assert frame.locator("html").get_attribute("data-pc-embedded") == ""
        assert not frame.locator(".pc-theme-toggle").is_visible()
        assert frame.locator("html").get_attribute("data-pv-theme") == "dark"
        bounds = page.locator("#configuratorFrame").bounding_box()
        assert bounds["height"] > 700 and bounds["width"] > 1300
        frame.locator("#tab-main").click()
        cpu = frame.locator("#readout-db_cpu")
        cpu.fill("0")
        page.locator("#configuratorStatus").wait_for(state="visible")
        cpu.fill("2")
        page.locator("#configuratorStatus").wait_for(state="hidden")
        frame.locator("#tab-artifact").evaluate("el => el.click()")
        import json
        calculated = json.loads(frame.locator("#panel-artifact .pc-code").inner_text())
        assert float(calculated["inputs"]["cpu_cores"]) == 2
        frame.locator("#tab-diff").click()
        assert frame.locator("#diff-input").input_value() == "name,setting,unit\n" + "\n".join(
            ','.join('"' + str(v or '').replace('"', '""') + '"' for v in row)
            for row in artifact["items"]["overview.pg_settings"]["result"]["rows"]
        ) + "\n"
        frame.locator("#diff-input").press("Escape")
        page.locator("#configuratorModal").wait_for(state="hidden")
        assert page.locator("#showConfigurator").evaluate("el => el === document.activeElement")
        page.locator("#themeToggle").check()
        page.locator("#showConfigurator").click()
        frame.locator('html[data-pv-theme="light"]').wait_for()
        assert not frame.locator(".pc-theme-toggle").is_visible()
        frame.locator("#tab-main").click()
        frame.get_by_role("button", name="Reset to report inputs").click()
        assert frame.locator("#field-db_cpu").input_value() == "8"
        page.locator("#closeConfigurator").click()
        assert not page.locator("body").evaluate("el => el.classList.contains('report-modal-open')")
        assert page.evaluate("window.injected") is None
        assert not errors
        assert not external
        browser.close()


def test_configurator_button_hidden_without_hardware(tmp_path: Path):
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = configurator_artifact()
    del artifact["items"]["os.total_ram"]
    path = tmp_path / "missing.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(path.as_uri())
        assert not page.locator("#showConfigurator").is_visible()
        assert page.locator("#configuratorFrame").get_attribute("srcdoc") is None
        browser.close()


def test_report_size_inputs_and_sliders_survive_reset_without_rounding_calculation(tmp_path: Path):
    sync_api = pytest.importorskip("playwright.sync_api")
    artifact = configurator_artifact()
    ram = 66806628352
    artifact["items"]["os.total_ram"]["result"]["rows"][0][0] = str(ram)
    settings = artifact["items"]["overview.pg_settings"]["result"]
    settings["columns"] += [{"name": "setting_normalized"}, {"name": "unit_normalized"}]
    settings["rows"] += [
        ["data_directory", "/srv/postgres", None, None, None],
        ["wal_segment_size", "1048576", "B", 1048576, "bytes"],
    ]
    for item_id, result in {
        "overview.database_volume": {"kind": "table", "columns": [
            {"name": "database_name"}, {"name": "database_size_bytes"}],
            "rows": [["postgres", 923 * 1024**3]]},
        "os.disk_usage": {"kind": "table", "columns": [
            {"name": "filesystem"}, {"name": "mount_point"}, {"name": "available_bytes"}],
            "rows": [["/dev/nvme0n1", "/", 8 * 1024**3]]},
        "snapshot_charts_db.wal_growth_rate": {"kind": "chart", "series": [
            {"unit": "bytes/s", "points": [{"value": 2.25 * 1024**2}]}]},
    }.items():
        artifact["items"][item_id] = {
            **artifact["items"]["charts.line"], "item_id": item_id, "item_key": item_id,
            "title": item_id, "collection_status": "ok", "result": result,
        }
        artifact["sections"][0]["items"].append(item_id)
    path = tmp_path / "sizes.html"
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1360, "height": 960})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.as_uri())
        page.locator("#showConfigurator").click()
        frame = page.frame_locator("#configuratorFrame")
        frame.locator("#diff-summary").wait_for()
        frame.locator("#tab-main").click()

        def assert_inputs():
            for dest, expected in {
                "db_ram": "62.22Gi", "db_size": "923Gi", "peak_wal_rate": "2.25Mi",
                "wal_disk_budget": "2Gi", "reserved_system_ram": "256Mi", "db_cpu": "8",
                "max_conns": "100", "reserved_ram_percent": "10",
            }.items():
                assert frame.locator(f"#readout-{dest}").input_value() == expected
            assert frame.locator("#field-wal_segment_size").input_value() == "1Mi"
            assert frame.locator("#field-db_ram").input_value() == "62"
            assert frame.locator("#field-db_size").input_value() == "6"
            assert frame.locator("#field-peak_wal_rate").input_value() == "2"
            assert frame.locator("#field-wal_disk_budget").input_value() == "2"
            frame.locator("#tab-artifact").evaluate("el => el.click()")
            inputs = json.loads(frame.locator("#panel-artifact .pc-code").inner_text())["inputs"]
            assert inputs["ram_bytes"] == ram
            assert inputs["db_size_bytes"] == 923 * 1024**3
            assert inputs["peak_wal_rate_bytes_per_second"] == 2.25 * 1024**2
            assert inputs["wal_disk_budget_bytes"] == 2 * 1024**3
            assert inputs["wal_segment_size_bytes"] == 1024**2
            frame.locator("#tab-main").click()

        assert_inputs()
        # An unrelated slider refresh must retain exact collected sizes too.
        frame.locator("#field-db_cpu").evaluate("el => el.dispatchEvent(new Event('input', {bubbles: true}))")
        assert_inputs()
        for _ in range(2):
            frame.locator("#readout-db_ram").fill("32Gi")
            frame.locator("#readout-db_size").fill("2Ti")
            frame.get_by_role("button", name="Reset to report inputs").click()
            assert_inputs()
        assert not errors
        browser.close()
