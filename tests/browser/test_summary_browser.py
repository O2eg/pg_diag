"""Embedded audit documents reuse report navigation and SQL/DDL hover previews."""
from __future__ import annotations

import os

import pytest

from pg_diag.render.html import render_html
from test_echarts_report import _artifact

pytestmark = pytest.mark.skipif(
    os.environ.get('PG_DIAG_BROWSER_TESTS') != '1', reason='set PG_DIAG_BROWSER_TESTS=1',
)


def test_summaries_markdown_links_previews_filters_and_navigation(tmp_path):
    sync_api = pytest.importorskip('playwright.sync_api')
    artifact = _artifact()
    artifact['items']['charts.line']['state'] = 'collapsed'
    artifact['query_texts']['-4023659083661925077'] = 'SELECT 42 AS answer;'
    artifact['object_ddl'] = {
        '16384': {'kind': 'relation', 'identifier': 'public.orders',
                  'ddl': 'CREATE TABLE public.orders(id bigint);'},
    }
    artifact['summaries'] = {
        'brief': {'markdown': '# Summary\n\n[Evidence](#item-charts.line)'},
        'detailed': {'markdown': (
            '# Detailed audit\n\n'
            '| Entity | Evidence |\n| --- | --- |\n'
            '| Query | **[`-4023659083661925077`](#item-charts.line?queryid=-4023659083661925077)** |\n'
            '| Object | [orders](#item-charts.line?oid=16384) |\n\n'
            '- First recommendation\n  - Nested evidence\n- Second recommendation\n\n'
            '```sql\nSELECT 42;\n```\n\n'
            '#### Details\n\n[Documentation](https://www.postgresql.org/docs/)\n\n'
            '<img src=x onerror="window.summaryInjected=true">\n'
            '</script><script>window.summaryInjected=true</script>\n'
        )},
    }
    path = tmp_path / 'report.html'
    path.write_text(render_html(artifact, validate=False))
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(path.as_uri())
        summary = page.locator('[data-section-id="__summary"]')
        assert page.locator('#app > details').first.get_attribute('data-section-id') == '__summary'
        assert page.locator('#reportNavTree .section-link').first.inner_text() == 'Summary'
        assert summary.evaluate('el => el.open')
        assert summary.locator('details.item[open]').count() == 0
        # Open through the contents; rendering is lazy and should not depend on order.
        page.locator('#reportNavToggle').click()
        page.locator('#reportNavTree [data-target-id="__summary.detailed"]').click()
        document = page.locator('[data-item-id="__summary.detailed"]')
        page.wait_for_function('document.querySelector("[data-item-id=\\"__summary.detailed\\"] table")')
        assert document.locator('table tbody tr').count() == 2
        assert document.locator('ul ul li').inner_text() == 'Nested evidence'
        assert document.locator('h4').inner_text() == 'Details'
        assert document.locator('pre code').inner_text() == 'SELECT 42;'
        assert document.locator('img, script').count() == 0
        assert page.evaluate('window.summaryInjected === undefined')
        external = document.get_by_role('link', name='Documentation')
        assert external.get_attribute('rel') == 'noopener noreferrer'
        query = document.locator('a[data-entity-kind="queryid"]')
        assert query.inner_text() == '-4023659083661925077'
        query.hover()
        page.locator('.hover-preview').wait_for(state='visible')
        assert page.locator('.hover-preview code').inner_text() == 'SELECT 42 AS answer;'
        oid = document.locator('a[data-entity-kind="oid"]')
        page.mouse.move(0, 0)
        page.locator('.hover-preview').wait_for(state='hidden')
        oid.scroll_into_view_if_needed()
        oid.hover()
        page.wait_for_function('document.querySelector(".hover-preview code").textContent.includes("CREATE TABLE")')
        assert page.locator('.hover-preview-title').inner_text() == 'DDL: relation public.orders'
        # Summary stays accessible even when collection filters hide its evidence.
        page.locator('#itemSearch').fill('no matching evidence')
        assert summary.is_visible()
        assert page.locator('details[data-item-id="charts.line"]').evaluate('el => el.classList.contains("hidden")')
        oid.click()
        page.wait_for_function('document.querySelector("details[data-item-id=\\"charts.line\\"]").open')
        assert page.locator('#itemSearch').input_value() == ''
        assert page.locator('details[data-item-id="charts.line"]').is_visible()
        assert page.evaluate('location.hash') == '#item-charts.line?oid=16384'
        assert not errors
        browser.close()


def test_report_without_summaries_has_no_summary_section(tmp_path):
    sync_api = pytest.importorskip('playwright.sync_api')
    path = tmp_path / 'report.html'
    path.write_text(render_html(_artifact(), validate=False))
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(path.as_uri())
        assert page.locator('[data-section-id="__summary"]').count() == 0
        browser.close()
