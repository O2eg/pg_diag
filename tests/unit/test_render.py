from __future__ import annotations

from pg_diag.render.html import render_html


def _without_vendor_bundles(html: str) -> str:
    blocks = [
        ('<script id="pg-diag-third-party-licenses"', "</script>"),
        ('<style id="highlight-theme"', "</style>"),
        ('<script id="apexcharts-library"', "</script>"),
        ('<script id="highlight-library"', "</script>"),
    ]
    result = html
    for start_marker, end_marker in blocks:
        start = result.find(start_marker)
        if start < 0:
            continue
        end = result.find(end_marker, start)
        if end < 0:
            continue
        result = result[:start] + result[end + len(end_marker) :]
    return result


def test_html_embedded_json_is_inert_and_escaped() -> None:
    artifact = {
        "artifact_schema_version": 1,
        "generator": {"name": "pg_diag", "version": "0.1.0"},
        "content": {"schema_version": 2, "checksum": "sha256:test"},
        "report": {"id": "test", "title": "Test"},
        "runtime": {
            "mode": "snapshot",
            "collection_mode": "remote-db-only",
            "collector_host": "collector-1",
            "collector_user": "oleg",
            "current_database": "pg_diag",
            "current_user": "app",
            "server_version": "PostgreSQL 18.4 (Ubuntu 18.4-1.pgdg24.04+1) on x86_64-pc-linux-gnu",
            "duration_seconds": 30,
            "interval_seconds": 5,
            "started_at": "2026-07-04T22:27:45.629777+00:00",
            "finished_at": "2026-07-04T22:28:20.925292+00:00",
        },
        "sections": [{"section_id": "s", "title": "S", "items": ["s.i"]}],
        "items": {
            "s.i": {
                "item_id": "s.i",
                "section_id": "s",
                "title": "Item",
                "source_kind": "query",
                "status": "ok",
                "result": {
                    "kind": "table",
                    "columns": [
                        {"name": "value"},
                        {"name": "query_id", "pg_type": "int8"},
                        {"name": "captured_at", "pg_type": "timestamptz"},
                    ],
                    "rows": [["</script><script>alert(1)</script>", "123", "2026-05-29T21:27:18.283630+00:00"]],
                    "row_count": 1,
                },
                "source_metadata": {
                    "query_id": "test.query",
                    "sql_file": "test/query.sql",
                    "variant_id": "test_query_all",
                    "tags": ["SQL", "Tables"],
                    "source_text": "select 1",
                    "source_language": "sql",
                    "instructions": {
                        "format": "markdown",
                        "path": "instructions/items/s/i.md",
                        "text": "# Item instruction\n\n## Checklist\n- Check **risk** and `query_id`.",
                    },
                },
                "diagnostics": [],
            }
        },
        "query_texts": {"123": "select * from pg_class where oid = $1"},
    }

    html = render_html(artifact)
    app_html = _without_vendor_bundles(html)

    assert '<script id="pg-diag-artifact" type="application/json">' in html
    assert "\\u003c/script\\u003e" in html
    assert "<script>alert(1)</script>" not in html
    assert "Filter rows" in html
    assert "All rows" in html
    assert 'id="itemTypeFilter"' in html
    assert 'id="tagFilter"' in html
    assert html.index('id="tagFilter"') < html.index('id="itemTypeFilter"') < html.index('id="statusFilter"')
    assert '<button id="expandAll" type="button" class="btn">Expand all</button>' in html
    assert '<button id="expandAll" type="button" class="btn primary">Expand all</button>' not in html
    assert 'id="visibleSummary"' in html
    assert "filter-summary-panel" in html
    assert "updateVisibleSummary(visibleTotal)" in html
    assert 'node.textContent = "Showing " + visibleTotal + " from " + visibleItems.length' in html
    assert "All tags" in html
    assert "hydrateTagFilter()" in html
    assert "TAG_ORDER" in html
    assert "details.__tags = itemTags(item)" in html
    assert "const tag = document.getElementById(\"tagFilter\").value" in html
    assert "const matchesTag = !tag || (item.__tags || []).includes(tag)" in html
    assert "All items" in html
    assert "Plain Text" in html
    assert "Table" in html
    assert "Chart" in html
    assert '<body class="report-nav-collapsed">' in html
    assert 'id="reportNav"' in html
    assert 'class="report-nav collapsed"' in html
    assert 'id="reportNavTree"' in html
    assert 'id="reportNavToggle"' in html
    assert "Contents" in html
    assert "Collapse contents" in html
    assert "Expand contents" in html
    assert "bindReportNavControls()" in html
    assert "setReportNavCollapsed" in html
    assert "report-nav-collapsed" in html
    assert ".report-nav.collapsed" in html
    assert "body.report-nav-collapsed .shell" in html
    assert "renderReportNav()" in html
    assert "renderReportNavButton" in html
    assert "navigateToReportNode(targetKind, targetId)" in html
    assert "findSectionElement(targetId)" in html
    assert "findItemElement(targetId)" in html
    assert "resetReportFilters()" in html
    assert 'target.scrollIntoView({behavior: scrollBehavior(), block: "start"})' in html
    assert "left: 0;" in html
    assert "top: 0;" in html
    assert "bottom: 0;" in html
    assert "border-radius: 0 8px 0 0" in html
    assert ".report-nav.collapsed .report-nav-title" in html
    assert "gap: 0;" in html
    assert 'totalBadge.textContent = "total: " + visibleItems.length' in html
    assert 'id="generatorInfo"' in html
    assert "generator.name || \"pg_diag\"" in html
    assert "generatorName + \" version \" + generatorVersion" in html
    assert "https://github.com/O2eg/pg_diag" in html
    assert "https://t.me/O2egg" in html
    assert "project-link-icon" in html
    assert "formatRuntimeValue(entry[0], entry[1])" in html
    assert "formatBrowserTimestamp(value)" in html
    assert "timeZoneName: \"short\"" in html
    assert 'id="runtimeDetails"' in html
    assert "collector_host" in html
    assert "collector_user" in html
    assert "shortServerVersion(runtime.server_version)" in html
    assert "formatSeconds(runtime.duration_seconds)" in html
    assert "formatSeconds(runtime.interval_seconds)" in html
    assert '"collector_host":"collector-1"' in html
    assert '"started_at":"2026-07-04T22:27:45.629777+00:00"' in html
    assert "refreshTable(state)" in html
    assert "tbody.replaceChildren()" in html
    assert "sort-button" in html
    assert "renderChart(result, item)" in html
    assert "ApexCharts v5.16.0" in html
    assert 'id="apexcharts-library"' in html
    assert 'id="highlight-library"' in html
    assert "pg-diag-third-party-licenses" in html
    assert "License: SEE LICENSE IN LICENSE" in html
    assert "https://cdnjs.cloudflare.com/ajax/libs" not in html
    assert "https://cdn.jsdelivr.net/npm" not in html
    assert "__APEXCHARTS_JS__" not in html
    assert "__HIGHLIGHT_JS__" not in html
    assert "__HIGHLIGHT_CSS__" not in html
    assert "__THIRD_PARTY_LICENSES__" not in html
    assert "new ApexCharts" in html
    assert "buildApexChartOptions" in html
    assert "apexChartType(chartKind)" in html
    assert "chartDatetimeBounds(series)" in html
    assert "min: datetimeBounds.min" in html
    assert "max: datetimeBounds.max" in html
    assert "const padding = 60000" in html
    assert "chartColors(series)" in html
    assert "entry._color || defaults[index % defaults.length]" in html
    assert '"stacked_area"' in html
    assert "kind === \"area\" || kind === \"stacked_area\"" in html
    assert "xType === \"datetime\" ? \"datetime\" : \"category\"" in html
    assert "apex-chart" in html
    assert "z-index: 60 !important" in html
    assert ".apexcharts-toolbar {\n      display: inline-flex !important;" in html
    assert "background: var(--button-bg) !important;" in html
    assert ".apexcharts-toolbar .apexcharts-menu-icon,\n    .apexcharts-toolbar .apexcharts-reset-icon," in html
    assert ".apexcharts-toolbar .apexcharts-selected,\n    .apexcharts-toolbar .apexcharts-menu-open" in html
    assert "background: var(--accent-soft) !important;" in html
    assert "apexcharts-menu" in html
    assert "justify-content: flex-start !important" in html
    assert "text-align: left !important" in html
    assert "padding: 10px 12px 6px" in html
    assert "zoom: {" in html
    assert "enabled: true" in html
    assert 'type: "x"' in html
    assert "autoScaleYaxis: unit !== \"%\"" in html
    assert "allowMouseWheelZoom: false" in html
    assert "toolbar: {" in html
    assert "selection: true" in html
    assert "zoomin: true" in html
    assert "zoomout: true" in html
    assert "pan: true" in html
    assert "reset: true" in html
    assert 'autoSelected: "zoom"' in html
    assert ".apexcharts-toolbar .apexcharts-selected svg" in html
    assert "chartTitle(item.title || \"\", unit)" in html
    assert "title: {text: \"\"}" in html
    assert "formatChartAxisValue(value, unit)" in html
    assert "formatChartTooltipValue(value, unit)" in html
    assert "formatCompactMetricValue(numeric, 1000)" in html
    assert "Highlight.js v11.11.1" in html
    assert 'id="sourceModal"' in html
    assert "const queryTexts = artifact.query_texts || {}" in html
    assert "query-id-button" in html
    assert "openQueryTextModal(queryId)" in html
    assert "Show query: " in html
    assert '"query_texts":{"123":"select * from pg_class where oid = $1"}' in html
    assert 'id="metaModal"' in html
    assert 'id="instructionModal"' in html
    assert "sourceActionLabel(item)" in html
    assert "Show SQL" in html
    assert "Show Bash" in html
    assert "Show meta" in html
    assert "Show Instruction" in html
    assert "openMetaModal(item)" in html
    assert "openInstructionModal(item)" in html
    assert "PgDiagMarkdown" in html
    assert "source.instructions.text_chars" in html
    assert '"path":"instructions/items/s/i.md"' in html
    assert "Item instruction" in html
    assert "itemMetaRows(item)" in html
    assert "appendMetaRows(rows, \"source\", item.source_metadata || {})" in html
    assert '"sql_file":"test/query.sql"' in html
    assert '"variant_id":"test_query_all"' in html
    assert '"tags":["SQL","Tables"]' in html
    assert "source.source_text_chars" in html
    assert "copyCurrentSource" in html
    assert "highlightElement" in html
    assert '"source_text":"select 1"' in html
    assert "formatNumberForColumn" in html
    assert "isTemporalColumn(column)" in html
    assert "formatTemporalValue(value, column)" in html
    assert 'pgType === "timestamp" || pgType === "timestamptz"' in html
    assert 'match[1] + " " + match[2]' in html
    assert "toFixed(3)" in html
    assert 'name.startsWith("seconds_")' in html
    assert 'name.includes("_seconds_")' in html
    assert '"captured_at","pg_type":"timestamptz"' in html
    assert "2026-05-29T21:27:18.283630+00:00" in html
    assert '<html lang="en" data-theme="dark">' in html
    assert 'id="themeToggle"' in html
    assert 'localStorage.setItem("pg_diag_theme"' in html
    assert "CELL_COLLAPSED_LINE_LIMIT = 6" in html
    assert "lineCount(text) > CELL_COLLAPSED_LINE_LIMIT" in html
    assert 'text.includes("\\\\n")' not in app_html
    assert "search-highlight" in html
    assert "itemSearchText(item)" in html
    assert "item.result" in html
    assert "refreshStaticHighlights(query)" in html
    assert "applyGlobalRowFilter" in html
    assert 'query: "SQL query"' in html
    assert 'script: "Bash"' in html
    assert "function addKv" not in app_html
    assert 'addKv(meta, "id"' not in app_html
    assert 'addKv(meta, "metric"' not in app_html
    assert "--item-summary-open-bg: #f3d46b" in html
    assert "--item-open-bg: #0f0a16" in html
    assert "--item-open-bg: #f2f2f5" in html
    assert "background: var(--item-open-bg)" in html
    assert "background: inherit" in html
    assert "details.item[open] > summary" in html
    assert "details.item[open]" in html
    assert "border-color: var(--item-summary-open-bg)" in html
    assert "DETAILS_ANIMATION_MS = 300" in html
    assert "bindAnimatedDetails()" in html
    assert "setDetailsOpen(details, !details.open, true)" in html
    assert "details.section {\n      box-sizing: border-box;" in html
    assert "details.item {\n      box-sizing: border-box;" in html
    assert "transition: background-color 300ms ease, color 300ms ease, border-color 300ms ease" in html
    assert ".details-content" in html
    assert ".details-content {\n      display: grid;\n      grid-template-rows: 1fr;\n      min-width: 0;" in html
    assert ".details-content-inner {\n      min-height: 0;\n      min-width: 0;" in html
    assert "grid-template-rows: 0fr" in html
    assert "grid-template-rows: 1fr" in html
    assert "details[open]:not(.is-opening):not(.is-closing) > .details-content > .details-content-inner" in html
    assert "details.item[open]:not(.is-opening):not(.is-closing)" in html
    assert "overflow: visible" in html
    assert "wrapDetailsContent(body)" in html
    assert "details.classList.add(\"is-opening\")" in html
    assert "window.setTimeout(" in html
    assert "chartResizeScopes" in html
    assert "flushChartResize" in html
    assert "isVisibleThroughDetails(entry.container)" in html
    assert 'diagnosticParts.push(key + ":\\n" + stringifyValue(value));' in html
    assert 'parts.push("diagnostic[" + index + "]:\\n" + diagnosticParts.join("\\n\\n"));' in html
    assert 'parts.push("output:\\n" + stringifyValue(result.data));' in html
    assert "getBoundingClientRect" not in app_html
    assert "offsetHeight" not in app_html
    assert "details.animate([" not in app_html
    assert 'window.dispatchEvent(new Event("resize"))' not in app_html
    assert "body.animate" not in app_html
    assert ".section-control-button.expand::before" in html
    assert ".section-control-button.collapse::before" in html
    assert 'button.className = "section-control-button expand"' in html
    assert 'button.dataset.action = action' in html
    assert 'button.setAttribute("aria-label", label)' in html
    assert 'buttonNode.dataset.action === "expand"' in html
    assert "updateSectionControlButton(button)" in html
    assert "querySelectorAll(\":scope > details.item\")" in html
    assert "DATA_TYPE_ORDER" in html
    assert "renderDataTypeIcons" in html
    assert "sectionDataTypes(section)" in html
    assert "itemDataType(item)" in html
    assert "details.dataset.itemType = itemDataType(item)" in html
    assert "const itemType = document.getElementById(\"itemTypeFilter\").value" in html
    assert "const matchesType = !itemType || item.dataset.itemType === itemType" in html
    assert "data-type-icon" in html
    assert "Plain text" in html
    assert 'class="page-scroll-controls"' in html
    assert 'id="scrollToTop"' in html
    assert 'id="scrollToBottom"' in html
    assert "bindPageScrollControls()" in html
    assert "updatePageScrollControls" in html
    assert "progress < 0.9" in html
    assert "setScrollButtonVisible" in html
    assert ".table-shell {\n      border: 1px solid var(--line);\n      border-radius: 8px;\n      overflow: hidden;\n      background: var(--panel);\n      width: 100%;" in html
    assert ".table-scroll {\n      max-height: 72vh;\n      width: 100%;\n      max-width: 100%;" in html
    assert ".item-error" in html
    assert "ERROR_ITEM_STATUSES" in html
    assert '"permission_denied"' in html
    assert "renderItemError(item)" in html
    assert "itemErrorDetailsText(item)" in html
    assert "traceback" in html
    assert "stderr" in html


def test_html_publicizes_legacy_internal_columns_before_embedding() -> None:
    artifact = {
        "artifact_schema_version": 1,
        "generator": {"name": "pg_diag", "version": "0.1.0"},
        "content": {"schema_version": 2, "checksum": "sha256:test"},
        "report": {"id": "test", "title": "Test"},
        "runtime": {"mode": "snapshot", "collection_mode": "remote-db-only"},
        "sections": [{"section_id": "s", "title": "S", "items": ["s.i"]}],
        "items": {
            "s.i": {
                "item_id": "s.i",
                "section_id": "s",
                "title": "Item",
                "source_kind": "query",
                "status": "ok",
                "result": {
                    "kind": "table",
                    "columns": [{"name": "epoch_ns"}, {"name": "tag_value"}],
                    "rows": [[1783182080458119000, "visible"]],
                    "row_count": 1,
                },
                "source_metadata": {},
                "diagnostics": [],
            }
        },
    }

    html = render_html(artifact)

    assert "epoch_ns" not in html
    assert "tag_value" not in html
    assert '"name":"value"' in html
    assert "visible" in html
