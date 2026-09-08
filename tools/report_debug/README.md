# Debugging Saved Reports

These tools consolidate verification scripts originally used with `report_trace`.
Report and output paths are arguments; no item counts, capture dates, credentials
or test-stand paths are hardcoded. No new workload or database connection is needed.

Run commands from the `pg_diag` checkout root. Install the project environment with
`python -m pip install -e '.[dev,browser]'`, and browser dependencies with
`python -m playwright install chromium`. JavaScript tools require Node.js.
Python commands support `--help`. Output paths are explicit.

| Tool | Purpose |
| --- | --- |
| `inventory.py` | JSON/HTML inventory, SHA256 hashes and preservation checks against a manifest |
| `scan_reports.py` | Completeness, table shape, NULL columns, intervals, numbers, time series and CPU state totals |
| `reconcile_metrics.py` | Recalculate charts from saved snapshots; independently check rates, ratios, plan references and query references |
| `evaluate.cjs` | Evaluate all nodes with current sources; detect rule errors, unbound items and inconsistent assessments of equivalent directions |
| `prepare_audit.cjs` | Execute the graph engine for master prompts; retain own findings, inherited colors, links, actual reads and source pointers |
| `summarize.py` | Assessment matrix, grey-node explanations, TSV and comparison with previous evaluations |
| `browser_audit.py` | Load HTML, check navigation APIs, lazy charts and auto_explain JSON/text/YAML/XML viewers, and compare with JSON evaluations |
| `navigation.py` | Use ordinary mouse clicks to reach every item from collapsed roots through cards; check filters and Full screen |
| `check_routes.cjs` | Check dashed and parent-child connections with full, partial and mixed expansion and varying card heights |
| `browser_routes.js` | Check rendered SVG paths; used by `browser_audit.py --links` |
| `refresh_html.py` | Update four graph blocks in one HTML while verifying that all other markup bytes stay unchanged |
| `replay_logs.py` | Replay saved CSV through the local/shell scanner; compare counts and coverage |
| `compare_logs.py` | Independently count CSV errors, warnings and auto_explain records in an explicit window |

`common.py` contains shared file and embedded graph-resource operations. Checks
do not modify input reports. `refresh_html.py` is a separate write command;
updating the original HTML requires a new backup path.

## Preparing Context for Master Prompts

Use [`diag_promt.md`](../../diag_promt.md) for performance or the independent
[`security_promt.md`](../../security_promt.md) for security. For each distinct
capture, supply the LLM with a prepared context, original report and selected prompt:

```bash
node tools/report_debug/prepare_audit.cjs /tmp/performance-context.json /path/to/report.json performance
node tools/report_debug/prepare_audit.cjs /tmp/security-context.json /path/to/report.html security
```

A JSON/HTML pair is one observation; prefer JSON when both exist. Output files
must be new; parent directories are created as needed. The script works from
other working directories when invoked by its path. It uses Node.js standard
modules and the checkout library, with no browser, database or external requests.
Input HTML scripts are never executed.

The `pg_diag/audit-context-v1` format contains:

- `source`: input path and SHA256; `engine`: API version and five engine-file hashes;
- `evaluation`: the complete, unchanged `PgDiagGraph.evaluate` result;
  `errors` separately lists evaluator failures;
- `focus`: scope nodes, own `warn`/`crit` candidates, inherited warnings,
  unassessed directions, context, links and item IDs for further reading;
- `reads`: actual rule accesses to sources, including ancestor inputs;
- `itemIndex`: JSON Pointer into the original artifact, status and scope for every item.

Performance includes CPU, RAM, Disk, Network and Database health, except
`network.access`. Security includes `database_security` and `network.access`.
The engine evaluates the entire artifact before scope filtering; neither inputs
nor assessments change. Nearby nodes from another scope can remain as context.
Global `evaluation.coverage` describes the whole graph. `focus.contextLinks`
is the initial neighborhood; `evaluation.links` retains all links for further investigation.

`bindings`, `inputBindings`, `reads` and `focus.evidenceItems` help locate sources;
they do not establish that every consulted item supports a finding. Raw rows,
plans, instructions, SQL, DDL and snapshots remain in the original report. The
LLM reads them during enrichment instead of relying only on rounded `facts` and
`reasons`. The prompts treat the context as a reasoning skeleton only: the
resulting documents (a detailed audit and a short summary) describe the
database, host, statements and settings, never the graph nodes. Project Markdown
documentation is in English; generated audits use the user's language unless
another is specified.

Preparation checks the artifact version and basic structure. Use
`pg-diag validate-artifact` for full schema validation. Exit code 0 means successful
evaluation, including runs with problem nodes; 1 means a context was saved with
evaluator errors; 2 means preparation failed. Unbound items appear in coverage
and require review. Existing outputs and input/companion paths are never
overwritten. New files are created with mode 0600.

## Reaching Every Item and Checking Arrows

```bash
mkdir -p /tmp/pg-diag-debug
.venv/bin/python tools/report_debug/navigation.py /path/to/report.html \
  --expected-items 320 --output /tmp/pg-diag-debug/navigation.json

.venv/bin/python tools/report_debug/browser_audit.py /path/to/report.html \
  --links --animation --output /tmp/pg-diag-debug/browser-links.json

.venv/bin/python tools/report_debug/browser_audit.py /path/to/report.html \
  --edges --animation --node network --node network.clients.capacity.sources.sessions \
  --output /tmp/pg-diag-debug/browser-tree.json

node tools/report_debug/check_routes.cjs \
  /path/to/report.json /tmp/pg-diag-debug/routes.json
```

`--expected-items` is optional; navigation covers all report items by default.
`navigation.py --icons` compares type icons in cards and item headings, including
their position right of the text and vertical centering. Each navigation record
contains the root path, node/item IDs, section expansion, visibility and heading
focus. This tests actual buttons, beyond bindings or `navigateToItem` calls.

For a targeted repeat:

```bash
.venv/bin/python tools/report_debug/navigation.py /path/to/report.html \
  --item replication.replication_slots --output /tmp/pg-diag-debug/one-item.json

.venv/bin/python tools/report_debug/navigation.py /path/to/report.html \
  --node network.clients.capacity.sources.outcomes \
  --output /tmp/pg-diag-debug/one-card.json

.venv/bin/python tools/report_debug/browser_audit.py /path/to/report.html \
  --links --animation --node disk.space --node health.replication \
  --output /tmp/pg-diag-debug/two-nodes.json
```

Link checks cover both themes, selection of either endpoint, open/closed cards
and partial/full expansion. They verify link sets, endpoints, arrow markers,
finite coordinates and intersections with circles and visible card regions.
An obstructed link may disappear during animation; all applicable links must
be visible once layout settles. `check_routes.cjs` also checks 5520 static
routes for the current 23 links, including cards up to 2400 px tall. Its `tree`
section checks solid connections with mixed expansion and each visible node's card.

Additional browser options:

- `--edges`: actual solid SVG paths, rounding, ports, intersections and visibility
  after animation. Checks all nodes unless limited by `--node ID`; also checks dashed links.
- `--arrow-zoom`: proportional scaling of the rendered arrowhead and causal-line
  thickness at 0.25×, 0.5×, 1× and 2×, using the report's marker and styles.
- `--center-cards`: opened cards center without changing zoom. `--node ID` selects
  nodes; `--screenshots` keeps the centered result without an extra Fit.
- `--node-links`: ordinary clicks on Related checks, Possible causes and Possible
  effects in both directions. Checks hidden-node expansion, centering at unchanged
  zoom and no jump before animation, in both themes with normal/reduced motion
  at 0.5× and 1.64×. `--node ID` limits starting nodes. The shared scenario in
  `browser_interactions.py` also supports browser regression tests.
- `--screenshots DIR`: selected branches in the dark theme after Fit for comparing
  layout and connections before and after algorithm changes.
- `--facts`: fact tables in all cards and both themes, including borders, padding,
  column proportions, overflow and clipping. Also checks the close button's
  top-right position and absence of text overlap. With `--node ID --screenshots DIR`,
  saves selected cards at 1:1 for styling review.
- `--explain-button`: ordinary clicks on Explain available, section/item expansion,
  hiding-filter reset, scrolling and focus in both themes. `--screenshots DIR`
  also saves header screenshots.
- `--all-details`: the second Expand all step, cards for all nodes, closing one
  card and routing among cards of different heights. `--node ID` limits checked nodes.

JSON also records allowed visible-link sets with example expansions: currently
35 causal-arrow sets, or 39 including Related checks, including the empty set.
Expanding a parent displays all its direct children. At most three links are
visible simultaneously; this does not limit the possible geometric arrangements.

## Checking New Diagnostics Across Reports

```bash
node tools/report_debug/evaluate.cjs /tmp/pg-diag-debug/before.json /path/to/*.json
# After changing rules:
node tools/report_debug/evaluate.cjs /tmp/pg-diag-debug/after.json /path/to/*.json
.venv/bin/python tools/report_debug/summarize.py /tmp/pg-diag-debug/after.json \
  --before /tmp/pg-diag-debug/before.json --output-dir /tmp/pg-diag-debug/summary

.venv/bin/python tools/report_debug/browser_audit.py '/path/to/**/*.html' \
  --current-source --evaluation /tmp/pg-diag-debug/after.json \
  --output /tmp/pg-diag-debug/browser.json
```

Without `--current-source`, checks use scripts embedded in HTML. With it, current
sources are substituted only in browser memory. `--evaluation` compares colors,
facts, reasons and limits with the companion JSON evaluation. Evaluation output
includes all nodes and can serve as a baseline before the next change.

`scan_reports.py --secret-file FILE` searches JSON and companion HTML for a known
secret. FILE contains one secret or JSON with `password` fields; secret values
are never printed in results. CPU totals require all five states; hidden zeros
count only with explicit `zero_series`, no gaps and matching observation counts.

Grey-node classification in `summarize.py` is a review heuristic; `hints` remains
the explanation source. Scan/reconcile discrepancies need review: aggregated
CPU can exceed 100%, and historical reports may use older formulas.

```bash
.venv/bin/python tools/report_debug/inventory.py '/path/to/*.json' '/path/to/*.html' \
  --output /tmp/pg-diag-debug/manifest.json
.venv/bin/python tools/report_debug/scan_reports.py '/path/to/*.json' \
  --output-dir /tmp/pg-diag-debug/scan
.venv/bin/python tools/report_debug/reconcile_metrics.py '/path/to/*.json' \
  --output /tmp/pg-diag-debug/reconciliation.json
.venv/bin/python tools/report_debug/inventory.py \
  --verify /tmp/pg-diag-debug/manifest.json --output /tmp/pg-diag-debug/preservation.json
```

Render a complete report with `pg-diag render --from-json INPUT.json --out NEW.html`;
validate its schema with `pg-diag validate-artifact INPUT.json`. To update only the graph:

```bash
.venv/bin/python tools/report_debug/refresh_html.py /path/to/report.html \
  --backup /tmp/pg-diag-debug/report-before.html
# Or save an updated copy:
.venv/bin/python tools/report_debug/refresh_html.py /path/to/report.html \
  --output /tmp/pg-diag-debug/report-current.html
```

For targeted template changes, such as a header button, add
`--template-before /path/to/template-before.html`. The tool applies only differences
from current `src/pg_diag/render/templates/report.html`. Save the previous template
before editing. Each fragment must match exactly once; changes involving data
or library substitutions are rejected. Updating the original still requires a backup.

## Checking Saved Logs

```bash
.venv/bin/python tools/report_debug/replay_logs.py /path/to/report.json /path/to/primary.csv \
  --from '2026-09-05 19:32:12' --to '2026-09-05 19:54:12' \
  --output /tmp/pg-diag-debug/log-replay.json

.venv/bin/python tools/report_debug/compare_logs.py /path/to/report.json /path/to/primary.csv \
  --from '2026-09-05T19:32:12Z' --to '2026-09-05T19:54:12Z' \
  --output /tmp/pg-diag-debug/log-comparison.json
```

`replay_logs.py` accepts times in the server-log timezone, as the scanner does.
Independent `compare_logs.py` requires explicit UTC offsets and normalizes them.
The window is not inferred from the last row of an incomplete capture. Compare
counts with coverage, top-N limits and collected items in mind. Replay uses
current scanner limits and full auto_explain detail. With a known per-minute
plan limit, `compare_logs.py --top-per-minute N` compares plan markers with an
independent selection of the longest CSV plans and records missing/extra points.

## Origins and Limits

These tools preserve capabilities from temporary `audit.cjs`, `browser_audit.py`,
`click_all_320.py`, `check_navigation_fullscreen.py`, `refresh_html.py`,
`write_audit.py`, `write_navigation_summary.py`, `deep_scan.py`, `reconcile.py`,
`raw_compare.py`, `replay_log_sources.py`, `render_and_browser.py` and
`final_checks.py` from `report_trace/review`. Duplicate inventory, completeness
and browser checks were consolidated above; results stay outside the source
tree. One-off corrections to old data were replaced with discrepancy checks
that do not write to artifacts.

Exit code 1 from navigation/browser/routes/evaluate/replay/inventory-verify means
a failed check. Scan/reconcile/summarize save candidates and matrices for manual
review. Read/parse failures also produce an error exit. Run ordinary Python
without `-O`, because some checks use assertions.
