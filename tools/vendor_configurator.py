"""Vendor the offline pg_configurator web page from an explicit local checkout.

Run: python tools/vendor_configurator.py ../pg_configurator
The calculation and UI modules are bundled by the upstream builder, unchanged.
Only the page entry point is adapted to accept report inputs before mounting.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "src/pg_diag/render"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    spec = importlib.util.spec_from_file_location("pg_configurator_build", checkout / "web/build.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.main()
    page = (checkout / "web/dist/pg-configurator.html").read_text()
    # Opt into the upstream embedded mode: the report owns the theme controls.
    assert page.count('<html lang="en"') == 1
    page = page.replace('<html lang="en"', '<html lang="en" data-pc-embedded', 1)
    bridge = (RENDER / "configurator/frame.js").read_text()
    assert page.count("page.mount();") == 1
    page = page.replace("page.mount();", bridge)
    page = page.replace("<head>", '''<head>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'">
<script type="application/json" id="pg-diag-configurator-context">__PG_DIAG_CONFIGURATOR_CONTEXT__</script>
<style>
.pc-report-inputs {margin: 16px 0; padding: 12px; border: 1px solid var(--pv-border); border-radius: 8px;}
.pc-report-inputs summary {cursor: pointer; font-weight: 600;}
.pc-report-inputs .pc-table {table-layout: fixed;}
.pc-report-inputs th:nth-child(1) {width: 28%;}
.pc-report-inputs th:nth-child(2) {width: 27%;}
.pc-report-inputs th:nth-child(3) {width: 45%;}
.pc-report-inputs td {overflow-wrap: anywhere;}
.pc-report-caveat {padding: 12px; border: 1px solid var(--pv-accent); border-radius: 8px;}
</style>''', 1)
    version = json.loads((checkout / "package.json").read_text())["version"]
    schema_version = json.loads((checkout / "web/data/input-schema.json").read_text())["package_version"]
    assert version == schema_version
    target = RENDER / "vendor/pg-configurator.html"
    target.write_text(page)
    (RENDER / "vendor/pg-configurator.LICENSE.txt").write_text((checkout / "LICENSE").read_text())
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
    provenance = [f"pg_configurator {version}", f"Revision: {revision}",
                  "Source: https://github.com/O2eg/pg_configurator", "License: MIT",
                  "Rebuild: python tools/vendor_configurator.py /path/to/pg_configurator",
                  "SHA-256 of upstream build inputs (including any local edits):"]
    paths = ["web/build.py", "web/configurator.template.html"]
    paths += ["web/" + p for p in builder.MODULES]
    paths += ["web/" + p for _, _, p in builder.DATA]
    paths += ["web/" + p for _, p in builder.STYLES]
    for path in paths:
        provenance.append(f"{hashlib.sha256((checkout / path).read_bytes()).hexdigest()}  {path}")
    provenance += ["", (checkout / "NOTICE").read_text()]
    (RENDER / "vendor/pg-configurator.NOTICE.txt").write_text("\n".join(provenance))
    print(f"Vendored pg_configurator {version}: {target.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
