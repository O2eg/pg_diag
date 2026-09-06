"""Page scrolling shares one cancellable animation across report entry points."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pg_diag.render.html import render_html
from test_echarts_report import _artifact

pytestmark = pytest.mark.skipif(
    os.environ.get("PG_DIAG_BROWSER_TESTS") != "1", reason="set PG_DIAG_BROWSER_TESTS=1"
)


def test_page_scroll_animation_navigation_interrupt_and_reduced_motion(tmp_path: Path):
    sync_api = pytest.importorskip("playwright.sync_api")
    path = tmp_path / "report.html"
    path.write_text(render_html(_artifact(), validate=False))
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.as_uri())
        page.evaluate("document.body.style.minHeight = '22000px'")
        page.locator("#scrollToBottom").evaluate("el => el.click()")
        page.wait_for_function("scrollY > 100 && scrollY < document.documentElement.scrollHeight - innerHeight - 100")
        page.wait_for_function("Math.abs(scrollY - (document.documentElement.scrollHeight - innerHeight)) < 1")

        # The top control uses the same motion; manual input must stop it.
        page.locator("#scrollToTop").evaluate("el => el.click()")
        page.wait_for_function("scrollY < 20000 && scrollY > 1000")
        stopped = page.evaluate("""() => {
          window.dispatchEvent(new WheelEvent('wheel', {deltaY: 1}));
          return scrollY;
        }""")
        page.wait_for_timeout(800)
        assert page.evaluate("scrollY") == stopped

        # Item navigation also opens and focuses the requested item after motion.
        page.evaluate("window.pgDiagReport.navigateToItem('charts.line')")
        page.wait_for_function("Math.abs(document.querySelector('[data-item-id=\"charts.line\"]').getBoundingClientRect().top) < 1")
        assert page.locator('[data-item-id="charts.line"] > summary').evaluate(
            "el => el === document.activeElement"
        )

        # Reduced motion skips animation, including long jumps.
        page.emulate_media(reduced_motion="reduce")
        page.locator("#scrollToBottom").evaluate("el => el.click()")
        assert page.evaluate("Math.abs(scrollY - (document.documentElement.scrollHeight - innerHeight)) < 1")
        page.locator("#scrollToTop").evaluate("el => el.click()")
        assert page.evaluate("scrollY") == 0
        assert not errors
        browser.close()
