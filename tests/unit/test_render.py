from __future__ import annotations

from pg_diag import runtime_config
from pg_diag.render.html import render_html


def test_report_collator_is_initialized_before_initial_render(repo_root) -> None:
    template = (repo_root / "src/pg_diag/render/templates/report.html").read_text(encoding="utf-8")

    assert template.index("let cachedReportCollator = null;") < template.index("renderSections();")
    assert template.count("let cachedReportCollator = null;") == 1


def _column(name: str, value_kind: str, encoding: str, **extra) -> dict:
    descriptor = {
        "name": name,
        "label": name,
        "value_kind": value_kind,
        "semantic_role": "identifier" if name == "query_id" else "state" if value_kind == "timestamp" else "label",
        "quantity": "identifier" if name == "query_id" else "timestamp" if value_kind == "timestamp" else "text",
        "unit": "none",
        "quality": "exact",
        "nullable": True,
        "encoding": encoding,
    }
    descriptor.update(extra)
    return descriptor


def _without_vendor_bundles(html: str) -> str:
    blocks = [
        ('<script id="pg-diag-third-party-licenses"', "</script>"),
        ('<style id="highlight-theme"', "</style>"),
        ('<script id="echarts-library"', "</script>"),
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
        "artifact_schema_version": runtime_config.ARTIFACT_SCHEMA_VERSION,
        "generator": {"name": "pg_diag", "version": "0.8.0"},
        "content": {
            "schema_version": runtime_config.SUPPORTED_CONTENT_SCHEMA_VERSION,
            "content_path": "/tmp/test-content",
            "checksum": "sha256:test",
            "report_id": "test",
            "document": {
                "report": {"id": "test", "title": "Test"},
                "runtime_policy": {},
                "defaults": {"table": {"page_size": 25}},
                "sections": {
                    "s": {
                        "title": "S",
                        "items": {
                            "i": {"query": "test.query", "tags": ["SQL", "Tables"]},
                        },
                    },
                },
                "catalogs": {
                    "queries": {"defaults": {"cost": "low"}},
                    "presentation": {"units": {"none": {}}},
                },
                "queries": {
                    "test.query": {
                        "title": "Item",
                        "display": {"default_sort": {"column": "value", "direction": "asc"}},
                        "variants": [
                            {"id": "test_query_all", "min_pg_version": 140000, "sql_file": "test/query.sql"},
                        ],
                    },
                },
                "instructions": {
                    "s.i": {"format": "markdown", "path": "instructions/items/s/i.md"},
                },
                "scripts": {},
                "metrics": {},
                "python_sources": {},
                "sampler_providers": {},
                "field_reference": {
                    "report": "Report metadata.",
                    "sections/*/items/*/query": "Query manifest id used by this item.",
                    "queries/*/variants[]/sql_file": "SQL file executed for this variant.",
                },
            },
            "provenance": {
                "report": ["report.yaml"],
                "defaults": ["report.yaml"],
                "sections": ["report.yaml"],
                "catalogs/queries": ["queries.yaml"],
                "queries/test.query": ["queries.yaml", "catalog/test.yaml"],
                "instructions/s.i": ["instructions/items/s/i.md"],
                "field_reference": ["field_reference.yaml"],
            },
        },
        "report": {"id": "test", "title": "Test"},
        "runtime": {
            "mode": "one-shot",
            "collection_mode": "remote-db-only",
            "collector_host": "collector-1",
            "collector_user": "oleg",
            "current_database": "pg_diag",
            "database_host_ip": "192.0.2.10",
            "database_hostname": "db-primary.example",
            "database_name": "pg_diag",
            "database_role": "Primary",
            "current_user": "app",
            "server_version": "PostgreSQL 18.4 (Ubuntu 18.4-1.pgdg24.04+1) on x86_64-pc-linux-gnu",
            "duration_seconds": 30,
            "interval_seconds": 5,
            "started_at": "2026-07-04T22:27:45.629777+00:00",
            "finished_at": "2026-07-04T22:28:20.925292+00:00",
        },
        "display": {"table": {"page_size": 25}},
        "sections": [
            {"section_id": "s", "title": "S", "state": "expanded", "items": ["s.i"]}
        ],
        "items": {
            "s.i": {
                "item_id": "s.i",
                "section_id": "s",
                "item_key": "i",
                "title": "Item",
                "source_kind": "query",
                "collection_scope": "once",
                "collection_status": "ok",
                "severity_level": "unknown",
                "state": "expanded",
                "result": {
                    "kind": "table",
                    "columns": [
                        _column("value", "text", "json_string"),
                        _column("query_id", "integer", "decimal_string", pg_type="int8"),
                        _column("snapshot_time", "timestamp", "json_string", pg_type="timestamptz"),
                        _column("captured_at", "timestamp", "json_string", pg_type="timestamptz"),
                    ],
                    "rows": [[
                        "</script><script>alert(1)</script>",
                        "123",
                        "2026-05-29T21:27:17.123456+00:00",
                        "2026-05-29T21:27:18.283630+00:00",
                    ]],
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
                "issues": {},
            }
        },
        "query_texts": {"123": "select * from pg_class where oid = $1"},
        "snapshot_schemas": {},
        "snapshots": [],
        "diagnostics": [],
    }

    html = render_html(artifact)
    app_html = _without_vendor_bundles(html)

    assert '<script id="pg-diag-artifact" type="application/json">' in html
    assert "\\u003c/script\\u003e" in html
    assert "<script>alert(1)</script>" not in html
    assert "Filter rows" in html
    assert "All rows" in html
    assert 'const pageSizeValues = ["25", "50", "100", "500", "all"]' in app_html
    assert '"15", "50"' not in app_html
    assert "const showFilter = rows.length > 1" in app_html
    assert "const showPaginationControls = rows.length > 25" in app_html
    assert 'const collectedAt = item.source_kind === "metric" ? null : item.collected_at' in app_html
    assert "formatBrowserTimestamp(rawValue)" in app_html
    assert 'String(column.pgType || "").toLowerCase() === "timestamptz"' in app_html
    assert "container.appendChild(empty)" in app_html
    assert '"Snapshot start time"' in app_html
    assert '"Snapshot finish"' in app_html
    assert '"Delta duration"' in app_html
    assert 'labels.className = "delta-window-labels"' in app_html
    assert "if (showFilter)" in app_html
    assert "if (showPaginationControls)" in app_html
    assert ".table-toolbar.no-pagination" in app_html
    assert ".table-toolbar.single-row" in app_html
    assert '--code-panel-bg: #f6f8fa' in app_html
    assert 'html[data-theme="light"] .scroll-jump' in app_html
    assert 'background: #ffffff' in app_html
    assert 'html[data-theme="light"] .source-code-shell .hljs' in app_html
    assert 'html[data-theme="light"] .meta-raw-shell .hljs' in app_html
    assert 'html[data-theme="light"] .hljs-keyword' in app_html
    assert 'html[data-theme="light"] .hljs-string' in app_html
    assert 'html[data-theme="light"] .hljs-comment' in app_html
    assert 'html[data-theme="light"] .hljs-subst' in app_html
    assert 'id="itemTypeFilter"' in html
    assert 'id="tagFilter"' in html
    assert html.index('id="tagFilter"') < html.index('id="itemTypeFilter"') < html.index('id="collectionStatusFilter"') < html.index('id="severityLevelFilter"')
    assert '<button id="expandAll" type="button" class="btn">Expand all</button>' in html
    assert '<button id="expandAll" type="button" class="btn primary">Expand all</button>' not in html
    assert 'id="visibleSummary"' in html
    assert "filter-summary-panel" in html
    assert "filter-summary-actions" in html
    assert html.index('class="filter-summary-actions"') < html.index('id="visibleSummary"')
    assert "header-theme-toggle" in html
    assert '<label class="theme-toggle header-theme-toggle"' in html
    assert "updateVisibleSummary(visibleTotal)" in html
    assert 'node.textContent = "Showing " + visibleTotal + " from " + visibleItems.length' in html
    assert "All tags" in html
    assert "hydrateTagFilter()" in html
    assert "TAG_ORDER" in html
    assert "details.__tags = itemTags(item)" in html
    assert "renderItemTags(item)" in html
    assert 'list.className = "item-tag-list"' in html
    assert 'badge.className = "item-tag"' in html
    assert 'list.setAttribute("aria-label", "Item tags")' in html
    assert "const stripMeta = Boolean(runtime.strip_meta)" in html
    assert "if (stripMeta || !sourceText(item))" in html
    assert "if (stripMeta || !instructionText(item))" in html
    assert "if (stripMeta) {\n        return null;\n      }" in html
    assert "if (buttons.childElementCount)" in html
    assert html.index("buttons.appendChild(sourceButton)") < html.index(
        "buttons.appendChild(instructionButton)"
    ) < html.index("buttons.appendChild(metaButton)")
    assert "const tag = document.getElementById(\"tagFilter\").value" in html
    assert "if (leftEmpty !== rightEmpty)" in html
    assert "if ((leftNumber === null) !== (rightNumber === null))" in html
    assert "const matchesTag = !tag || (item.__tags || []).includes(tag)" in html
    assert "updateFilteredTagHighlights(tag)" in html
    assert 'badge.classList.toggle("filter-match", matches)' in html
    assert ".item-tag.filter-match" in html
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
    assert 'summaryLabel.textContent = "Collection status:"' in html
    assert 'id="severitySummary"' in html
    assert 'summaryLabel.textContent = "Severity levels:"' in html
    assert 'SEVERITY_SUMMARY_ORDER = ["ok", "medium", "high", "unknown"]' in html
    assert "renderSeveritySummary()" in html
    assert "severity-count" in html
    assert ".badge.severity-ok" in html
    assert ".severity-dot.severity-ok" in html
    assert 'return "OK"' in html
    assert ".summary-label" in html
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
    assert '<h1 id="reportTitle">Test</h1>' in html
    assert '<div id="reportTitleContext" class="report-title-context"></div>' in html
    assert "reportExtendedTitle()" in html
    assert '["IP", runtime.database_host_ip]' in html
    assert '["Host", runtime.database_hostname]' in html
    assert '["DB", runtime.database_name]' in html
    assert '["Role", runtime.database_role]' in html
    assert "collector_user" in html
    assert "shortServerVersion(runtime.server_version)" in html
    assert "formatSeconds(runtime.duration_seconds)" in html
    assert "formatSeconds(runtime.interval_seconds)" in html
    assert '"collector_host":"collector-1"' in html
    assert '"started_at":"2026-07-04T22:27:45.629777+00:00"' in html
    assert "refreshTable(state)" in html
    assert "tbody.replaceChildren()" in html
    assert "sort-button" in html
    assert 'column.name === "snapshot_time"' in html
    assert 'container.className = "snapshot-table-result"' in html
    assert 'label.className = "snapshot-time-label"' in html
    assert 'item && item.collection_scope === "once"' in html
    assert '? "One-shot time"' in html
    assert ': "Snapshot time"' in html
    assert "return renderTimeContextLabel(labelName, display.text, display.title)" in html
    assert ".snapshot-time-label" in html
    assert "renderChart(result, item)" in html
    assert 'version:"6.1.0"' in html
    assert 'id="echarts-library"' in html
    assert 'id="highlight-library"' in html
    assert "pg-diag-third-party-licenses" in html
    assert "License: Apache-2.0" in html
    assert "Copyright 2017-2026 The Apache Software Foundation" in html
    assert "Copyright 2010-2016 Mike Bostock" in html
    assert "https://cdnjs.cloudflare.com/ajax/libs" not in html
    assert "https://cdn.jsdelivr.net/npm" not in html
    assert "__ECHARTS_JS__" not in html
    assert "__HIGHLIGHT_JS__" not in html
    assert "__HIGHLIGHT_CSS__" not in html
    assert "__THIRD_PARTY_LICENSES__" not in html
    assert "ApexCharts" not in html
    assert 'window.echarts.init(pending.container, null, {renderer: "svg"})' in html
    assert "buildEChartsOptions(entry)" in html
    assert "echartsChartType(chartKind)" in html
    assert "chartDatetimeBounds(series)" in html
    assert "min: datetimeBounds.min" in html
    assert "max: datetimeBounds.max" in html
    assert "const padding = 60000" in html
    assert "chartColors(series)" in html
    assert '(result.chart || {}).series_order === "configured"' in html
    assert 'chartKind === "stacked_column" || chartKind === "stacked_bar"' in html
    assert "left._average - right._average || left._sourceIndex - right._sourceIndex" in html
    assert "right._average - left._average || left._sourceIndex - right._sourceIndex" in html
    assert "names.reverse()" in html
    assert "entry._color || defaults[colorIndex % defaults.length]" in html
    assert '"stacked_area"' in html
    assert 'chartKind === "area" || chartKind === "stacked_area"' in html
    assert 'type: xType === "datetime" ? "time" : "category"' in html
    assert "echarts-chart" in html
    assert "z-index: 60 !important" in html
    assert ".pg-diag-echarts-tooltip" in html
    assert "background: var(--panel) !important;" in html
    assert 'type: "inside"' in html
    assert 'filterMode: "filter"' in html
    assert "zoomOnMouseWheel: false" in html
    assert "moveOnMouseMove: false" in html
    assert "toolbox: {" in html
    assert "dataZoom: {" in html
    assert "myPan: {" in html
    assert "myZoomIn: {" in html
    assert "myZoomOut: {" in html
    assert "myExport: {" in html
    assert 'title: "Export"' in html
    assert "saveAsImage: {" not in html
    assert 'for (const format of ["svg", "png", "csv"])' in html
    assert "downloadEChartsImage(entry, format)" in html
    assert 'renderer: format === "png" ? "canvas" : "svg"' in html
    assert 'backgroundColor: "#ffffff"' in html
    assert 'text: "#21182f"' in html
    assert 'type: "plain"' in html
    assert "eChartsLegendLayout(entry, legendData)" in html
    assert "CHART_LEGEND_ROW_HEIGHT_PX" in html
    assert "CHART_LEGEND_MAX_VISIBLE_ROWS = 6" in html
    assert ".chart-legend-panel" in html
    assert "overflow-y: auto" in html
    assert "scrollbar-color: var(--line-strong) var(--panel-soft)" in html
    assert ".chart-legend-panel::-webkit-scrollbar-thumb" in html
    assert 'panel.setAttribute("role", "group")' in html
    assert "createEChartsLegendPanel(entry)" in html
    assert 'entry.chart.dispatchAction({type: "legendToggleSelect", name: seriesName})' in html
    assert "show: exporting" in html
    assert 'entry.chart.dispatchAction({type: "dataZoom"' in html
    assert "dataZoomSelectActive: false" in html
    assert "bindEChartsPan(entry)" in html
    assert "entry.panDrag = {" in html
    assert "range.end - range.start >= 99.999" in html
    assert "zoomEChart(entry, 0.8)" in html
    assert '"mousemove",\n          moveEChartsPan,\n          {capture: true, passive: false}' in html
    assert "function moveEChartsPan(event)" in html
    assert "downloadEChartsCsv(entry)" in html
    assert 'new Blob([csv], {type: "text/csv;charset=utf-8"})' in html
    assert 'icon: "path://M2 8h7V2h6v6h7L12 20z"' in html
    assert "chartTitle(item.title || \"\", axisScale.label)" in html
    assert "formatChartAxisValue(value, unit, axisScale)" in html
    assert "formatChartTooltipValue(entry.value, unit, scale)" in html
    assert "buildSortedEChartsTooltip(params, unit, xType, scale)" in html
    assert "chartScalableUnitLabel(unit, quantity)" in html
    assert 'formatter: (params) => formatChartAxisValue(params.value, unit, axisScale)' in html
    assert "right.value - left.value || left.seriesIndex - right.seriesIndex" in html
    assert 'type: isBar ? "shadow" : "cross"' in html
    assert "formatChartTimeCoordinate(value)" in html
    assert ".pg-diag-chart-tooltip-row" in html
    assert "enableChartTooltipScrolling(pending.shell)" in html
    assert 'className: "pg-diag-echarts-tooltip"' in html
    assert "enterable: true" in html
    assert 'trigger: "axis"' in html
    assert 'target.closest(".pg-diag-chart-tooltip-rows")' in html
    assert "rows.scrollTop = next" in html
    assert "event.stopImmediatePropagation()" in html
    assert "{capture: true, passive: false}" in html
    assert "pointer-events: auto !important;" in html
    assert "chartXGrid(result.series || [], xType)" in html
    assert "hasFiniteValue: false" in html
    assert "stored.hasFiniteValue = stored.hasFiniteValue || Number.isFinite(numeric)" in html
    assert "const firstFinite = grid.findIndex" in html
    assert "return grid.slice(firstFinite, lastFinite + 1)" in html
    assert "valuesByX.has(coordinate.key) ? valuesByX.get(coordinate.key) : null" in html
    assert "Number.isFinite(point.y) && point.y !== 0" in html
    assert "Array.isArray(point.value) ? point.value[1] : point.value" in html
    assert "rawValue === null || rawValue === undefined" in html
    assert "formatChartSeriesLabel(seriesName)" in html
    assert 'const queryIdMatch = /^(.*)\\.(-?\\d+)$/.exec(rawName)' in html
    assert 'baseLabel + " / SQL: " + shortQuery' in html
    assert ".replace(/</g, \"&lt;\")" in html
    assert "chartAxisScale(series, unit" in html
    assert 'unit === "bytes" || unit === "bytes/s"' in html
    assert '["B/s", "KiB/s", "MiB/s", "GiB/s"' in html
    assert "Highlight.js v11.11.1" in html
    assert 'id="sourceModal"' in html
    assert "html.report-modal-open,\n    body.report-modal-open" in html
    assert "overscroll-behavior: none;" in html
    assert "overscroll-behavior: contain;" in html
    assert 'const REPORT_MODAL_IDS = ["sourceModal", "metaModal", "instructionModal"]' in html
    assert "syncReportModalScrollLock()" in html
    assert 'showReportModal(modal, "closeSource")' in html
    assert 'showReportModal(modal, "closeMeta")' in html
    assert 'showReportModal(modal, "closeInstruction")' in html
    assert "hideReportModal(modal)" in html
    assert "const queryTexts = artifact.query_texts;" in html
    assert "query-id-button" in html
    assert "openQueryTextModal(queryId)" in html
    assert "Show query: " in html
    assert '"query_texts":{"123":"select * from pg_class where oid = $1"}' in html
    assert 'id="metaModal"' in html
    assert 'id="metaTotalTab"' in html
    assert 'id="metaRawTab"' in html
    assert 'role="tablist" aria-label="Metadata view"' in html
    assert '>Total</button>' in html
    assert '>Raw</button>' in html
    assert 'selectMetaTab("total")' in html
    assert 'selectMetaTab("raw")' in html
    assert "buildRawItemConfiguration(currentMetaItem)" in html
    assert "renderAnnotatedYaml(raw.document, raw.provenance)" in html
    assert 'copyRawRoot(document, "report")' not in html
    assert "document.catalogs = selectedCatalogs" not in html
    assert "relevantRawRuntimePolicy(item, sourceKind, sourceManifest)" in html
    assert "relevantRawDefaults(item, section, itemDefinition, sourceManifest)" in html
    assert "projectedRawQueryManifest(queryManifest, null)" in html
    assert "samplerProviderForOutput(sourceSampler)" in html
    assert "projectedRawProvenance(document, relatedPaths)" in html
    assert 'code.className = "language-yaml"' in html
    assert '" Source" + (sources.length > 1 ? "s" : "")' in html
    assert "const contentDocument = contentConfig.document;" in html
    assert "const contentProvenance = contentConfig.provenance;" in html
    assert "const contentFieldReference = contentDocument.field_reference;" in html
    assert '"queries/test.query":["queries.yaml","catalog/test.yaml"]' in html
    assert ".meta-tab[aria-selected=\"true\"]" in html
    assert ".meta-raw-shell" in html
    assert 'id="instructionModal"' in html
    assert "sourceActionLabel(item)" in html
    assert "Show SQL" in html
    assert "Show Bash" in html
    assert "Show meta" in html
    assert "Show Instruction" in html
    assert "openMetaModal(item)" in html
    assert "openInstructionModal(item)" in html
    assert "PgDiagMarkdown" in html
    assert "renderReportItemReference" in html
    assert 'link.href = "#" + reportItemAnchorId(itemId)' in html
    assert 'navigateToReportNode("item", itemId)' in html
    assert 'unavailable.className = "report-item-link unavailable"' in html
    assert 'unavailable.setAttribute("aria-disabled", "true")' in html
    assert 'details.id = reportItemAnchorId(item.item_id || "")' in html
    assert "source.instructions.text_chars" in html
    assert '"path":"instructions/items/s/i.md"' in html
    assert "Item instruction" in html
    assert "itemMetaRows(item)" in html
    assert "appendMetaRows(rows, \"source\", item.source_metadata || {})" in html
    assert "renderItemIssues(item)" in html
    assert "SEVERITY_LEVEL_ORDER" in html
    assert "severity-dot" in html
    assert "Severity level" in html
    assert "collectionStatusFilter" in html
    assert "severityLevelFilter" in html
    assert ".item-issues" in html
    assert '"sql_file":"test/query.sql"' in html
    assert '"variant_id":"test_query_all"' in html
    assert '"tags":["SQL","Tables"]' in html
    assert "source.source_text_chars" in html
    assert "copyCurrentSource" in html
    assert "highlightElement" in html
    assert '"source_text":"select 1"' in html
    assert "formatMeasurement(value, column, unit)" in html
    assert "formatAdaptiveIntegerQuantity(exactInteger, unit)" in html
    assert "formatAdaptiveMilliseconds(numeric)" in html
    assert "setHighlightableText(label, tableColumnLabel(column))" in html
    assert 'column.unit !== "milliseconds"' in html
    assert 'text: sign + formatGroupedInteger(whole) + fractionText + " " + suffixes[index]' in html
    assert 'parts.push(String(minutes) + " min")' in html
    assert "isTemporalColumn(column)" in html
    assert "formatTemporalValue(value, column)" in html
    assert 'column.valueKind === "timestamp"' in html
    assert "formatBrowserTimestamp(text)" in html
    assert "roundHalfAway" in html
    assert "parseExactInteger" in html
    assert "formatExactBytes" in html
    assert '"name":"captured_at"' in html
    assert '"pg_type":"timestamptz"' in html
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
    assert 'python: "Python"' in html
    assert "Show Python" in html
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
    assert "itemRenderOptions(item)" in html
    assert "itemEmptyMessage(item, \"No rows\")" in html
    assert "itemEmptyMessage(item, \"No chart data\")" in html
    assert "shouldRenderReasonAsResult(item)" in html
    assert "renderReasonResult(item)" in html
    assert 'collectionStatus(item) !== "unsupported"' in html
    assert 'box.className = "item-error"' in html
    assert ".badge.unsupported," in html
    assert 'status === "unsupported"' in html
    assert 'sourceKind === "python"' in html
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
    assert 'new Set(["error"])' in html
    assert '"permission_denied"' not in app_html
    assert "statusLabel(status.status)" in html
    assert "renderItemError(item)" in html
    assert "itemErrorDetailsText(item)" in html
    assert "traceback" in html
    assert "stderr" in html
