# Diagnostic Graph Specification

Status: normative contract for the diagnostic graph module that ships inside the
pg_diag HTML report (`src/pg_diag/render/graph/`). The module turns a rendered
report artifact into a compact cause tree with six roots — `cpu`, `ram`,
`disk`, `network`, `database_health`, `database_security` — evaluates every node from the
raw item data, and renders the result as an interactive top-down graph above the
report sections.

The module is self-contained: it knows the graph, the traversal order, the
evaluation rules, and the artifact item formats (table columns, chart series and
points, plain text). It does not know how items are collected and it never
reuses the severity that the content pack assigned to an item; every score is
computed here from the item data.

## 1. Files

| File | Purpose |
| --- | --- |
| `graph.json` | Declarative graph: nodes, parent links, cause links, item bindings, requirements. Data only. Validated by `tests/unit/test_diagnostic_graph.py` against `content/report.yaml`. |
| `pg-diag-graph-data.js` | Status-aware artifact access, decoding, facts, timestamp alignment, windows and unit conversion. UMD global `PgDiagGraphData`; no DOM access. |
| `pg-diag-graph-rules.js` | Thresholds, shared calculations and one registry of raw evaluators. UMD global `PgDiagGraphRules`; depends only on data. |
| `pg-diag-graph.js` | Public `PgDiagGraph.evaluate` API, traversal, pressure/caps, propagation, coverage and hints. UMD/CommonJS; depends on data and rules, with no DOM access. |
| `pg-diag-graph-render.js` | Renderer (global `PgDiagGraphRender`): SVG edges and nodes, expandable inline detail cards with bound items and hints, animated tree layout. Uses the report theme through CSS variables only. |
| `pg-diag-graph.css` | Structural styles plus the score gradient stops as `--dg-*` variables. |
| `DIAGNOSTIC_GRAPH_SPEC.md` | This document. |

The renderer inlines the assets and the graph definition into
`templates/report.html` through `render/html.py` placeholders
(`__PG_DIAG_GRAPH_CSS__`, `__PG_DIAG_GRAPH_DEFINITION__`, `__PG_DIAG_GRAPH_JS__`,
`__PG_DIAG_GRAPH_RENDER_JS__`). The page script exposes
`window.pgDiagReport.navigateToItem(itemId)` so the graph can scroll the report
to a bound item with the same behaviour as a related-item link in an instruction.

`__PG_DIAG_GRAPH_JS__` contains data, rules and engine in that order. Python
concatenates these resources; no bundler, external script fetch or new build step
is needed. CommonJS resolves the same dependencies with `require`. The public
`PgDiagGraph` entry point and evaluation result retain their shape.

## 2. Graph model

`graph.json`:

```json
{
  "schema_version": 1,
  "roots": ["cpu", "ram", "disk", "network", "database_health", "database_security"],
  "nodes": [
    {
      "id": "disk.write.checkpoints",
      "parent": "disk.write",
      "label": "Checkpoints",
      "summary": "Requested checkpoints, sync time and write bursts.",
      "evaluator": "checkpoints",
      "requires": ["snapshots"],
      "bindings": [
        {"id": "snapshot_charts_db.checkpoint_trigger_events", "role": "primary"},
        {"id": "server_log.checkpoints", "role": "support"}
      ]
    }
  ],
  "links": [
    {"from": "disk.read.queries", "to": "cpu.seq_scans", "label": "seq scans read blocks"}
  ]
}
```

Rules:

- `id` is unique; dots separate the path but carry no semantics for the engine.
- Every non-root node has exactly one `parent`; the parent graph MUST be a tree
  with the six roots as its only sources. `links` are additional directed cause
  edges between any two nodes and MUST NOT create a parent cycle (they are not
  part of the tree and never propagate scores).
- `bindings[]` lists the report items that carry the evidence for the node. One
  item MAY be bound to several nodes (bloat is a disk cause and a health
  problem). `role` is `primary` (the node is about this item), `support`
  (adds evidence), or `fact` (inventory read by extractors, never scored on its
  own). A binding MAY carry `weight` (0–1): the score assigned when the item has
  finding rows and no per-row `risk_level` column.
  Mixed log tables (`server_lifecycle`, `system_incidents`, and the compatibility
  `crash_recovery_events`) use named, event-aware evaluators instead of a blanket
  row weight; a binding may provide context without proving a fault in that branch.
- Every read by a rule or its helpers MUST be declared in the node's bindings
  or an ancestor's bindings. Shared resource inputs belong to grouping nodes as
  facts; specific diagnostic sources belong to the consuming node. Ancestor
  facts authorize reads but do not open a child's evaluation gate. Tests audit
  actual reads through `evaluate(..., {onRead(nodeId, itemId, method)})`, including
  empty-source fallbacks and resource-pressure calculations.
- Every item id declared in `content/report.yaml` MUST be bound to at least one
  node, and every bound id MUST exist there. Items that exist in the catalog but
  not in a given artifact (older artifact, filtered report, one-shot mode) are
  reported as absent, never as an error.
- `requires` names what the node needs to have data: `snapshots` (metric
  items exist only in the snapshots run mode), `host` (local or remote
  collection mode), `log` (`--log-depth-time-min`), or an extension name
  (`pg_stat_statements`, `pg_stat_kcache`, `pg_wait_sampling`,
  `pg_buffercache`). The engine turns unmet requirements into user hints.
- `evaluator` names a function in the engine registry. Nodes without it use
  the `generic` evaluator (section 4). Roots and pure grouping nodes use
  `aggregate`.
- `params` specifies inputs for a parameterized evaluator. Throughput uses
  `metric`; interface counters use `event` (`errors`/`drops`); TCP/UDP settings
  use `protocol`; client waits use `waitEvent` (`ClientRead`/`ClientWrite`).
  Missing or invalid values produce an evaluator error. No rule infers its
  behavior from a node id suffix; renaming nodes must preserve calculations.
- `pressure`, when present, identifies the symptom against which a candidate
  contributor is assessed: `cpu_user`, `cpu_system`, `cpu_iowait`, `ram`, or
  `disk`. Damping is applied once, after the evaluator, not once per helper.
  Repeated evidence under different resources uses that branch's pressure.
  The damping factor is `0.2 + 0.8 × pressure` (0.5 when the pressure is
  unknown, as in one-shot reports): a contributor on an idle resource keeps its
  explanation but can never reach `warn` on its own.
- `cap`, when present, bounds the node's own score after damping. It marks
  findings that are real but are not a failure of this root: configuration
  advice (`health.observability` 0.3) and security checks repeated under
  Network (`network.access.*` 0.6). Children still propagate above a cap.

Resource branches follow observed symptoms, then possible contributors:

- CPU: User CPU (user + nice), System CPU (system + IRQ + softirq), I/O wait,
  and Hypervisor steal. User work leads to backend/query, vacuum and other
  process evidence; kernel work to contention, sessions, network and paging.
  I/O wait has its own read/write subtrees and swap evidence, including query
  scans, cache misses, checkpoints, WAL and temporary files. It is not part
  of user CPU. The historical `cpu.utilization` id now denotes User CPU.
- RAM: available memory/OOM, swap occupancy, and cache misses. Memory budgets,
  backend population, huge pages, cache sizing and working-set causes sit
  below the corresponding symptom.
- Disk: device latency, read I/O, write I/O and free space. Reads lead to
  readers, scans, indexes, cache misses, vacuum, backups and temporary files;
  writes to data-file writers, WAL and spills. Bloat also belongs below
  capacity. Bindings are intentionally repeated where evidence is relevant.
- Network: traffic (receive, transmit, packet processing), interface health
  (errors, drops, NIC/address inventory), client connections (ClientWrite,
  ClientRead, capacity, reconnects, frequent calls, transport failures), WAL
  transport (send backlog, receiver, synchronous replies, topology, streaming
  disconnects), TCP/UDP configuration, and access/encryption (listeners,
  firewall, TLS/GSS, authentication/HBA, local sockets). Every Network-tagged
  catalog item MUST be bound under this root, alongside related client,
  replication, security and workload evidence. Existing CPU/health/security
  bindings remain, with cause links between the related branches.

## 3. Traversal

1. `PgDiagGraph.evaluate(artifact, definition)` indexes `artifact.items` and
   classifies every binding: `present` (collection status `ok` and the result
   has at least one table row, a usable chart series, or non-empty text),
   `empty` (status `ok`/`empty` without data), `skipped`, `unsupported`,
   `error`, or `absent` (not in the artifact).
2. Leaves are evaluated first, then parents, then roots (post-order over the
   parent tree). A node's own evaluator runs when at least one `primary` or
   `support` binding is collected (`present` or `empty`); empty finding lists
   may establish that nothing was found. An evaluator with no usable metric
   returns `null`, not a healthy score. Facts-only inventory nodes use their
   fact bindings as the collection gate; otherwise the node is `no_data`.
3. A node's final score is the maximum of its own score and its children's
   scores, so a red leaf lights the path to its root. A node whose own
   evaluator had no data but has scored children takes the children's score and
   keeps the `no_data` mark for its own evidence.
4. Roots aggregate their children. Cause links are reported on the node
   (`causes`, `caused_by`) for rendering only.
5. Coverage: for every node the engine reports `present`, `missing`, and
   `hints` — one hint per unmet requirement, derived from the artifact runtime
   (`runtime.mode`, `runtime.collection_mode`, `runtime.log_collection`) and the
   bound items' statuses and `reason` texts. A mode hint appears only when the
   whole category (snapshots, host, log) is missing from the node; when any
   `server_log.*` item was collected, an absent log item is a catalog
   difference and produces no log hint.

The evaluator context is created by `createAccess`: `rows`, `series` and `text`
read only sources with status `ok`. `item` also permits status `empty` for hidden
zero metadata. Failed, skipped, unsupported and unknown-status payloads cannot
contribute even if retained in the artifact. Raw decoders remain public for
inspection; diagnostic rules use the context. Each series needs two finite
samples, except event charts and event counter deltas which need one. Valid positive observations may
still be used with collection warnings; hidden zeros require complete coverage.

## 4. Evaluation

Scores are numbers in `[0, 1]`; `status` is `ok` (< 0.34), `warn` (< 0.67),
`crit` (≥ 0.67), or `no_data`. Helpers:

- `scale(value, warn, crit)` maps a metric to `[0, 1]`: 0 below `warn`, 1 above
  `crit`, linear in between (reversed when `warn > crit`).
- Rules return raw scores. The engine applies resource pressure once, then the
  node cap, then takes the maximum with children. There are no registration-time
  wrappers or evaluator-local damping defaults.
- Chart statistics use finite points only: `mean`, `max`, `p95`, `last`, `n`.
  A series with fewer than 2 finite points is treated as absent.
  Event charts (`tooltip_kind = log_event` or `query_event`) and event counter
  deltas are exceptions: one finite point is already measured evidence,
  including many deadlocks or writer-pressure events in a single interval.
  Counter deltas with unit `count` are identified by `semantic_role`; older
  artifacts may identify event counts by quantity or an event-specific unit.
  A count-valued gauge such as sessions still requires two finite samples.
- `alignSeries` matches equivalent UTC instants, not array positions. All
  internal sums explicitly choose `missing: "strict"` for components of a total,
  or `missing: "observed"` for independent events and sparse top-N wait profiles. Strict sums retain gaps as
  unknown; ordinary time-series statistics still require two comparable points
  after alignment. Duplicate timestamps are ambiguous and remain unknown.
  The public `sumSeries` helper retains index fallback for legacy value-only
  arrays; artifact chart series always use timestamps.
- Wait-profile LWLock/Buffer/IPC counts are evaluated independently of the
  availability of a total. Their share uses sums over the observed window, not
  means of series with different sample counts, and describes the observed
  top-N session samples rather than all backend activity.
- Window and unit helpers live in the data module: actual delta duration precedes
  runtime fallback, log wall-clock durations do not use the browser timezone,
  relation blocks use `block_size`, and I/O operations use byte counters or
  `op_bytes`.
- Table cells are decoded by column `encoding`: `decimal_string` → number
  (`Number()`; values above 2^53 lose precision, which is acceptable for
  scoring), `json_number` as is, `json_boolean` as is, others as text.
- `generic`: for each `primary`/`support` binding with rows, the severity is the
  worst `risk_level` cell in the rows (`high` 1.0, `medium` 0.6, `low` 0.3,
  `ok`/`unknown` 0) when the table has that column, otherwise `binding.weight`
  scaled by the row count (weight ≥ 1 is critical on its own; lighter weights
  use `weight × (0.6 + 0.4 × min(1, rows / 10))`). Bindings with neither a
  weight nor a `risk_level` column are context and never score. The node score
  is the maximum. Bindings with role `fact` are ignored.
- Named evaluators implement the runbook rules (CPU busy share and load per
  core, system share, disk latency by media type, cache hit ratio, checkpoint
  requested/timed ratio, backend writes share, connection usage, lock wait
  duration, xid age, replication lag, and so on). Each returns `score`,
  `reasons[]` (short sentences with the measured values), `facts{}`
  (named values for the panel), and `evidence[]` (item ids that produced the
  reasons).
- CPU busy is work time: `100 - idle - iowait - steal`, or the sum of available
  work-time series when idle is absent. I/O wait is not CPU work (runbook 1.1);
  hypervisor steal remains a separate pressure signal (1.2).
- The CPU symptom nodes score their own counters separately; a high load
  average alone does not prove CPU execution. Optional component counters are
  paired by timestamp. I/O wait uses explicit graph triage thresholds (5/20),
  not a claim that the runbook specifies a universal saturation threshold.
  I/O contributors are weighted by I/O wait, not by user CPU utilization.
- Swap occupancy is not swap-in/out activity. Missing swap counters stay
  unknown; zero swap is valid evidence. Available memory and OOM are assessed
  separately from swap. Throughput without device-pressure evidence likewise
  does not establish a healthy disk.
- Log errors are classified per row by SQLSTATE class, or by an anchored message signature
  when the log line prefix carries no `%e`: PANIC, internal/system errors,
  corruption and disk-full (class XX, 58, 53100, 57P02) score 1.0; out of memory
  and connection exhaustion (53200, 53300) 0.8; server unavailable (57P03),
  and other FATAL 0.6; deadlock (40P01) uses the shared rate rule below;
  timeouts and cancellations (57014,
  55P03) 0.4; administrator terminations (57P01) and client connection loss
  (class 08) 0.3; authentication failures (class 28) 0.15 because the security
  root owns them. Everything else (constraint, syntax, data, privilege errors)
  is an application error: it stays visible at 0.1 and only a flood (20–200 per
  minute) reaches `warn`. Chronology, top errors and query termination counts
  overlap and may each be capped; per class the larger count is kept, never a
  sum. A missing chronology must not hide PANIC/FATAL in top errors or
  termination events. A known nonzero SQLSTATE takes precedence over message
  text; SQL identifiers containing incident phrases are not server incidents.
  Query terminations score 0.4, rising with their rate.
- Deadlocks are resolved by the server: any deadlock stays visible at 0.3 and
  the rate per minute (0.1 warn, 5 critical) decides the rest, separately for
  the log window and the snapshot window, consistently in locks and errors.
  Delta rates use the source item's `delta_window.duration_seconds`; only legacy
  artifacts without that field fall back to the actual runtime window, then the
  configured duration. An explicitly invalid delta window stays unknown.
- Autovacuum lag counts tables whose dead tuples passed the threshold with at
  least 10 000 dead rows and no vacuum running; insert-triggered vacuums are
  routine and only reported. The worst overdue factor and the dead-tuple share
  on large tables carry the score, together with bloat.
- Sequential scans: the sequential share of tuple reads can only warn; the
  number of tables where sequential reads beat index fetches (> 1M tuples) and
  the worst table's volume carry the weight. Foreign keys without a supporting
  index on tables above 10k rows are missing-index evidence under the same
  nodes, never under database health.
- Heavy statements: with pg_stat_kcache the CPU seconds per second of the top
  statements and the sum over the listed statements against the core count
  are the primary CPU evidence; mean execution time alone can only warn.
- Checkpoints: when the log names the trigger, only `wal` checkpoints count as
  requested against `time` ones; immediate/force/shutdown/end-of-recovery
  checkpoints are explicit and excluded. One requested checkpoint in a window
  (or a handful since a stats reset) is too few to judge. Log reasons replace
  snapshot trigger counts only when the scan covers the entire snapshot window,
  ranking and per-item counts are complete, no rows were capped, and the log
  accounts for the observed trigger counts. Only checkpoint starts inside that
  window qualify; restartpoints and RLE groups crossing its boundary cannot
  explain snapshot counts. Server-local log times use the collected
  `log_utc_offset_seconds`; an unknown log zone cannot replace snapshot counts.
  A log window never replaces counters since reset.
- Relation block counts use the server's `block_size`. Without that setting,
  the graph reports blocks and skips byte thresholds. `pg_stat_io` byte shares
  prefer native byte counters, otherwise use each row's `op_bytes`; they never
  assume 8192 bytes per operation or use a partial denominator.
- Backend writes from `pg_stat_io` use the `normal` context only: bulk loads
  write through ring buffers and do not show a lagging checkpointer.
- Huge pages and THP are memory pressure only with at least 4 GB of shared
  memory; below that the same findings are advice (0.15).
- Mixed log signals are classified by `event_type`/`incident_type` and, for
  legacy rows, explicit message signatures. OOM belongs to memory pressure,
  disk-full to free-space pressure, crash/corruption to health. Readiness,
  reload, redo and end-of-WAL observations alone are not crashes; SIGKILL alone
  does not prove OOM. A generic missing-file error does not prove any of these.
- Last replayed transaction age grows on an idle primary and is not, by itself,
  replication lag (runbook 4.5). Age is scored only with positive unapplied WAL
  in the same observation; chart samples are paired by timestamp, not index or
  end-of-window state. Byte lag and paused replay remain independent signals.
  An age-only chart without corroborating data is informational, not an OK verdict.
- Deadlock charts and endpoint deltas observe the same counter. Use their
  maximum as the window observation, never their sum; keep the separate log
  window labelled and do not add it to snapshot counts.
- Shared diagnostic calculations run in each consuming node's context, keeping
  reasons, facts and dependency reads together. Raw artifact decoding is cached
  by result identity; artifacts are treated as immutable during evaluation.
  No node-scoped evidence or pressure score is cached across nodes, so traversal
  order cannot change the result.
- Fact extractors read inventory items: CPU count from `os.cpu_info`, RAM from
  `os.memory_info`/`os.total_ram`, disk media from `os.lshw_disk` (NVMe / SSD /
  rotational), build flags from `overview.pg_config` (`--enable-cassert`,
  `--enable-debug`), process counts by role from `backend_os.postgres_process_tree`,
  settings from `overview.pg_settings` (normalized values), THP and huge page
  state from `os.postgresql_huge_pages`. Extractors return `null` when the item
  is absent; evaluators degrade to what is available and say so in `reasons`.

Thresholds are constants in the engine (`THRESHOLDS`), documented inline with
the runbook section they come from, and covered by unit tests.

### Network evaluation constraints

- Traffic is per interface and direction, never a sum across virtual/physical
  interfaces. NIC `configuration.speed` must match the exact interface name
  before assessing throughput against link speed; hardware `capacity` is not
  the current negotiated speed. RX and TX are not added for full-duplex usage.
- Error/drop rates come from adjacent `/proc/net/dev` samples, not cumulative
  totals. Counter rollback and missing data stay unknown. The report suppresses
  zero lines; only explicit `zero_series` metadata with at least two observed
  samples covering every collected interval and no missing points permits a
  zero-rate verdict. Missing partition rows count as gaps. Sampler warnings or
  errors prevent a hidden-zero verdict. The same rule applies to hidden CPU
  components; rounded totals near 100% do not prove an unreported component is
  zero. Old empty charts must not manufacture healthy interface status.
- Packet processing uses the p95 of joint packet/system CPU pressure at matching
  timestamps (at least two pairs). Independent peaks at different times do not
  establish packet-related CPU pressure.
- Any observed interface error gives a warning; peak 10 errors/s gives a
  critical triage flag. Drops stay visible from the first one (0.2), warn from
  10/s and are critical at 100/s, because Linux counts unknown protocols, VLAN
  tags and filtered frames as drops on healthy hosts. Link-use thresholds
  (70/95) and ClientWrite thresholds (3/20 sessions, visible from one) are
  explicit heuristics, not universal limits. Errors/drops are not added as
  disjoint losses. Linux procfs combines some RX dropped/missed counters;
  filtering or unsupported protocols may contribute.
- ClientRead, configuration and inventory are facts without an automatic
  health verdict. ClientWrite can reflect a slow application consumer or large
  results as well as transport. Cumulative calls are not RTT measurements.
- Only transport SQLSTATEs/anchored log messages and abandoned-session deltas
  feed client transport failures. Overlapping log sources use the maximum as a
  lower bound, not a sum. Logged transport failures warn from the first one
  (0.4, rising to 0.8 at 50); abandoned sessions alone are visible (0.2) and
  warn only when dozens of clients vanish. Statement/lock timeouts and
  administrative kills do not prove network failure. Streaming failures filter typed sender/receiver
  disconnects; archive failures and recovery conflicts are not network faults.
- WAL send/receive backlog may also reflect sender CPU or receiver writes.
  Receive backlog uses `latest_end_lsn - written_lsn`; `written_lsn - flushed_lsn`
  is a local flush fact. Legacy receiver rows without a written LSN cannot use
  their receive/flush gap as transport pressure. Flush/replay delay and old message
  timestamps alone do not score transport. SyncRep uses the same rule in Network
  and Health: recovery applies configuration after promotion, while primary-side
  quorum severity respects actual waiters, commit requirements and source risk.
  SyncRep waits can involve remote disk/replay, not just the network.
- TCP settings are not retransmission, RTT or socket-queue measurements; those
  measurements are not collected by these items. The graph must say so.

Semantics: [Linux interface statistics](https://docs.kernel.org/networking/statistics.html),
[PostgreSQL wait events and statistics](https://www.postgresql.org/docs/18/monitoring-stats.html),
and runbook sections 3.6, 4.5 and 6.

## 5. Rendering

- Layout: roots in the top row, children in depth rows below, siblings side by
  side, and parents centred above their first/last child. Subtree spans reserve
  space for wrapped labels. Parent→child edges are straight solid segments
  clipped at the circles. There are no list-style elbows or column boxes.
- Cause links are shown only for the selected node, as dashed arrows routed
  through level gutters and clear vertical lanes with rounded corners. They
  must not cross unrelated nodes or labels.
- Node: a circle filled with the score gradient (green → yellow → red), grey
  when `no_data`, dashed stroke when the node is missing data because of the
  run or collection mode. Root circles are enlarged with wrapped names inside;
  other names are below their circles. A +N badge denotes collapsed children.
  No computed score percentages are displayed anywhere (circles, tooltips,
  panel or child list). Measured values in reasons/facts retain their units.
  Status labels are OK / Warning / Critical / No data; security and health
  findings must never be labelled "Bottleneck".
- Canvas: fixed-height viewport with drag-to-pan, wheel zoom anchored at the
  pointer, and in-canvas minus/plus, Fit and 1:1 controls. Button zoom anchors
  at the viewport centre; the scale readout is a multiplier. Start at a readable
  scale, not a microscopic fit of all trees. Fit provides the full overview.
  A drag must not select or collapse a node. Keyboard +/- zoom, Home/0 fits,
  arrows pan and Enter/Space activates a focused node. User viewport state
  survives node selection; resizing refits only in Fit mode. Re-rendering
  disconnects the old resize observer.
- Click: a details card unfolds immediately below the node, inside the SVG
  scene via `foreignObject`, and scales/pans with the graph. It
  shows the node summary, status, reasons, facts, the
  hints for missing data, and the bound items as chips (title, collection
  status, presence); clicking a chip calls `navigateToItem`. Hover shows the
  reasons as a tooltip. All content is included, without a fixed-height internal
  scroll area. The card has a fixed width in graph coordinates and its actual
  HTML height is measured before layout. A second click (including on a leaf)
  closes the card; selecting another node replaces it. There is no separate
  details panel below the canvas.
  If children raise the score above the node's own score, the panel states
  that explicitly without a numeric score. Warning/critical branches initially
  expand to reveal their possible contributors.
- Opening/closing cards and branches animates node positions, connected edges
  and card reveal over 300 ms. Subtree spans reserve the card width, and deeper
  rows move below its full height so cards cannot cover other nodes or edges.
  The clicked circle stays anchored in screen space and the zoom is unchanged.
  Interruptions start from the current interpolated positions, not the previous
  destination. Closing cards cannot receive clicks. `prefers-reduced-motion`
  disables animation; re-render/destroy cancels frames and disconnects card
  measurement observers. Item buttons remain clickable after pan/zoom; SVG
  viewport gestures do not consume button presses or keyboard activation.
- The panel above the sections carries a legend, the overall status line
  ("3 of 6 roots have data; snapshots mode adds 19 nodes"), and a
  collapse control; the rendered state is kept in `localStorage` only for the
  collapse flag.
- No external libraries. The renderer uses only CSS variables defined by the
  report theme (`--bg`, `--text`, `--accent`, `--ok-fg`, `--warn-fg`, ...) plus
  its own `--dg-*` tokens; it works in both report themes.

## 6. Tests

- `tests/unit/test_diagnostic_graph.py`: `graph.json` structure, parent tree
  acyclicity, six roots, every catalog item bound, every bound id in the
  catalog, evaluator names exist in the engine, HTML placeholders replaced, and
  a subprocess run of the node test suite when `node` is available.
- `tests/js/diagnostic_graph.test.js` (`node --test tests/js`): decoding,
  chart statistics, fact extractors on real item shapes, evaluators on fixture
  artifacts (snapshots with data, one-shot without metric items, remote-db-only
  without host items), post-order/max propagation, hint generation, log-source
  fallback and overlap, typed log signals, idle versus lagging standby, CPU
  component separation, I/O-wait-specific contributors, missing pressure,
  separate swap/available-memory signals, and complete explanations in repeated
  branches. `diagnostic_graph_render.test.js` tests sibling alignment, subtree
  bounds, wrapped label separation, full-height inline cards and obstacle-free
  cause routes with cards open.
- `tests/browser/test_diagnostic_graph_browser.py` (Playwright, opt-in like the
  ECharts test): the graph renders, node click opens the panel, item chip
  click scrolls to the item. Both themes must have a separate graph stylesheet,
  visible parent/cause strokes, a no-data color, and an opaque panel background;
  assertions inspect computed styles, not only HTML placeholder strings.
  Normal and wide viewports must also pass zoom/pan, drag-versus-click, fit,
  contained root labels, selected-only cause links, non-percentage statuses
  and inline card placement/scale checks. Animation tests inspect intermediate
  positions, open/close symmetry, anchor preservation, rapid interruptions,
  reduced motion, complete card content and cleanup during re-render.

`tests/js/diagnostic_graph_architecture.test.js` checks the single registry and
explicit parameters, real dependency reads, failed-payload isolation across all
rules, sample eligibility, timestamp/missing-value policies, source windows,
pressure/cap/child ordering, renamed/reordered graph equivalence and browser UMD
versus CommonJS parity. Existing metric regression and renderer tests remain.

## 7. Change policy

- Adding an item to the catalog requires binding it here; the unit test fails
  otherwise.
- Renaming an item id requires updating `graph.json`; the engine tolerates ids
  that are missing in an artifact but the test does not tolerate ids missing
  in the catalog.
- New thresholds go into `THRESHOLDS` with a comment naming the runbook rule.
