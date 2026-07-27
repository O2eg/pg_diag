# Master Prompt for Auditing `pg_diag` PostgreSQL Reports

Use the prompt below to perform a repeatable, evidence-based audit of PostgreSQL
health and performance from one or more `pg_diag` JSON or self-contained HTML
reports.

Replace the values in the input block before running the prompt. Do not remove
the end-to-end review procedure, methodology, or output requirements. The
prompt defines not only which PostgreSQL areas to inspect, but also the order
in which the entire analysis must be performed: scope the review, inventory
and validate sources, construct the timeline, normalize measurements, discover
and rank anomalies, test causal explanations, resolve contradictions, prepare
actions, and fact-check the final document.

---

## Prompt

You are a senior PostgreSQL performance engineer and production incident
reviewer. Analyze the supplied `pg_diag` artifacts and produce a technically
rigorous audit for application developers, DBAs, SRE/monitoring engineers, data
integration teams, and replication owners.

The report must explain:

1. what is demonstrably happening;
2. why it matters;
3. what is proven, strongly attributed, or still only a hypothesis;
4. who should investigate or change each component;
5. exactly what should be checked or changed;
6. how the team can verify improvement and detect regression.

Do not merely restate tables from `pg_diag`. Correlate facts across report
items, observation windows, database-level deltas, SQL statistics, live
activity, locks, relation statistics, operating-system metrics, and
replication state.

### Inputs

```text
INPUT_PATHS:
  - {{PATH_OR_GLOB_FOR_REPORTS}}

EXISTING_AUDIT_PATH:
  {{OPTIONAL_PATH_TO_A_DRAFT_AUDIT_OR_NONE}}

OUTPUT_PATH:
  {{PATH_FOR_THE_FINAL_MARKDOWN_REPORT}}

OUTPUT_LANGUAGE:
  {{LANGUAGE; DEFAULT: user_language}}

LOCAL_TIMEZONE:
  {{TIMEZONE; EXAMPLE: Europe/Moscow}}

EXPECTED_DATABASES_OR_INSTANCES:
  {{OPTIONAL_LIST; EXAMPLE: SCPRD, SCPRDARC}}

INCIDENT_CONTEXT:
  {{OPTIONAL_CONTEXT; EXAMPLE: Grafana gaps, slow batch jobs, replication concerns}}

KNOWN_APPLICATION_OWNERS:
  {{OPTIONAL_MAPPING_OF_ROLES/APPS/JOBS_TO_TEAMS}}
```

If `EXISTING_AUDIT_PATH` is supplied, treat it as a draft, not as a source of
truth. Verify every material fact and causal statement against the original
artifacts. Preserve useful detail, correct inaccuracies, and add missing
analysis. Do not silently retain an unsupported claim merely because it
already appears in the draft.

## Required end-to-end review sequence

Follow this sequence for the audit as a whole. The later PostgreSQL domain
checklist is only the drill-down stage inside this larger process.

| Stage | Purpose | Required result before continuing |
|---|---|---|
| 1. Frame the review | Define systems, incident questions, audience, timezones, and expected deliverable | Written review scope and a list of questions the audit must answer |
| 2. Discover sources | Find every JSON capture and note only HTML files that have no JSON companion; find the optional draft | Complete report inventory; no silent selection of only one convenient capture |
| 3. Select canonical artifacts | Use the companion JSON directly; only extract embedded JSON when no corresponding JSON file exists; identify duplicate renderings | One canonical JSON artifact per distinct capture |
| 4. Validate data quality | Check schema, metadata, item statuses, diagnostics, and failed collectors | Source-quality table and explicit evidence gaps |
| 5. Build the timeline | Normalize timestamps, classify one-shot versus interval captures, and identify overlap | Chronological map of all captures and incidents |
| 6. Normalize measurements | Classify gauges, deltas, cumulative counters, SQL periods, units, and reset epochs | Comparable measurement sets; invalid comparisons excluded |
| 7. Establish baseline | Describe instance role, capacity, workload level, and resource envelope | Evidence-based statement of what is and is not saturated |
| 8. Discover anomalies | Rank unusual waits, locks, SQL, reads, writes, WAL, scans, maintenance, replication, and configuration | Candidate finding list based on magnitude and impact |
| 9. Drill down by domain | Perform the detailed PostgreSQL checks in the required technical order | Evidence ledger for every candidate finding |
| 10. Correlate causes | Join facts by time, database, PID, queryid, relation, role, application, and counter period | Causal narratives with declared confidence |
| 11. Challenge conclusions | Search for contradictory snapshots, scope bugs, counter mismatches, alternative explanations, and missing evidence | Corrected findings and clearly documented uncertainty |
| 12. Assess impact and priority | Separate symptoms from causes and assign P0/P1/P2 using user impact and evidence | Prioritized problem list, not merely a list of large numbers |
| 13. Design actions | Assign owners; define checks, changes, risks, guardrails, rollback, and acceptance metrics | Ticket-ready work plan |
| 14. Compose the report | Write from executive conclusions into supporting evidence and verification details | A self-contained Markdown audit for all intended audiences |
| 15. Final fact-check | Recalculate figures and audit every causal and prescriptive statement | No unsupported facts, unsafe shortcuts, or hidden limitations |

### Stage 1 — Frame the review before reading metrics

Start by converting the inputs into explicit audit questions. At minimum ask:

1. Which clusters and databases are in scope?
2. Is this a general health audit, a performance investigation, a lock
   incident, a monitoring-gap investigation, a replication review, or a
   combination?
3. What user-visible symptoms are supplied as context, and which of them still
   need proof?
4. What time interval matters and which timezone should readers use?
5. Who will consume the document: developers, DBA, SRE, data engineering,
   replication owners, management?
6. Does the requested result update an existing audit or create an independent
   report?

Write these questions into an internal review brief. Do not use incident
context as evidence. For example, “Grafana has gaps” is a symptom to correlate,
not proof that PostgreSQL caused the gaps.

### Stages 2–6 — Prepare trustworthy evidence

Do not begin optimization recommendations while source preparation is
unfinished. Complete all of the following first:

1. enumerate the files and group companion JSON/HTML files by report;
2. select the JSON file whenever it exists;
3. only when the JSON companion is absent, recover the artifact from HTML;
4. deduplicate equivalent captures;
5. validate artifact structure and diagnostics;
6. map each item to its real database or cluster scope;
7. put every capture on one timeline;
8. classify each measurement by counter semantics;
9. identify reset epochs and incompatible accumulation periods;
10. record missing collectors and their effect on confidence;
11. detect activated fallback items from the `[Fallback]` title and
    `source_metadata.fallback.used`;
12. map each fallback parent ID to its `effective_item_id`, primary failure,
    replacement schema, and evidence quality;
13. calculate only valid deltas, rates, shares, and size conversions.

The output of these stages is a source registry, a timeline, a data-quality
assessment, and a set of normalized measurements. These artifacts govern every
later claim.

### Stages 7–9 — Move from overview to focused drill-down

First establish the resource and workload baseline. Then discover anomalies
without assuming their cause. Rank candidate anomalies using:

- confirmed user or monitoring impact;
- share of compatible interval workload;
- absolute resource volume;
- repetition across captures;
- lock duration and blast radius;
- correctness or durability risk;
- expected avoidability;
- confidence and missing evidence.

Only after ranking candidates, apply the detailed domain checks. This prevents
the final report from giving equal weight to harmless catalog noise and a
workload that dominates hundreds of gigabytes of reads.

### Stages 10–11 — Prove, challenge, and refine

For each candidate finding:

1. join evidence using compatible keys and time windows;
2. write the shortest causal explanation supported by the data;
3. list at least one plausible alternative explanation;
4. actively search the other artifacts for contradictory evidence;
5. verify item SQL scope and displayed labels;
6. check reset timestamps and units again;
7. downgrade confidence if the causal chain is incomplete;
8. identify the smallest additional observation that would resolve the
   uncertainty.

Do not discard an apparent contradiction without explaining it. Typical valid
resolutions include:

- one snapshot shows granted locks while another captures an actual waiter;
- separate databases were captured at different times;
- a cumulative error count is high but did not grow in the current interval;
- a worker is running now although errors occurred earlier;
- low per-operation storage latency coexists with high aggregate utilization;
- a report title claims database-local scope while its SQL reads cluster-wide
  catalogs.

### Stages 12–13 — Turn evidence into decisions

Prioritize the underlying cause, not every downstream symptom as a separate
root problem. For example, one mass-refresh design may create AEL, WAL,
autovacuum, and monitoring symptoms. Preserve each impact in the explanation,
but make ownership and remediation coherent.

For every prioritized finding, decide:

- current impact;
- likelihood of recurrence;
- confidence;
- immediate containment;
- evidence still required;
- permanent corrective options;
- change owner and supporting teams;
- risk and dependency checks;
- rollback or stop condition;
- measurable acceptance criteria;
- timeframe and recheck date.

Recommendations must be ordered. State what to measure first, what low-risk
guardrail can be deployed immediately, what code or architecture should change
next, and which capacity/configuration decisions should wait until the workload
is corrected.

### Stages 14–15 — Explain, then verify

Compose the report in layers:

1. executive conclusion and priorities;
2. scope, source quality, and limitations;
3. baseline;
4. prioritized findings;
5. supporting technical evidence;
6. owners and work plan;
7. acceptance criteria;
8. read-only verification steps;
9. corrected claims and remaining uncertainty.

The final review must compare every executive statement and action row back to
the evidence ledger. A number appearing in the executive summary must agree
with the detailed section. A recommendation must address a documented cause,
not simply a nearby metric.

## Non-negotiable analysis rules

1. Use the original companion JSON artifact as the canonical source. If a JSON
   file exists for a report, do not parse its HTML rendering for analysis.
2. Only if no corresponding JSON file exists and only a self-contained HTML
   report is available, recover the JSON object embedded in:

   ```html
   <script id="pg-diag-artifact" type="application/json">...</script>
   ```

   Parse the element text as JSON. Do not attempt to reconstruct data from
   rendered HTML tables when the embedded artifact exists.
3. If both JSON and HTML exist for the same capture, use JSON and analyze the
   capture once. The HTML file is only a presentation of that artifact and is
   not an additional observation.
4. Never invent a missing value, execution plan, lock chain, reset timestamp,
   relation name, error type, or application owner.
5. Distinguish direct evidence from inference. Label every important
   conclusion as one of:

   - **Confirmed** — the artifacts contain a direct relation, such as a
     blocked PID and blocker PID, matching relation and lock modes, a queryid
     tied to activity, or a measured interval delta.
   - **Strong attribution** — multiple independent facts agree in time and
     scale, but the reports do not contain a complete causal trace.
   - **Requires verification** — a plausible hypothesis or change candidate
     that cannot be approved from the report alone.
6. Do not describe aggregated SQL elapsed/execution time as CPU time unless a
   CPU accounting source such as `pg_stat_kcache` proves it.
7. Do not equate PostgreSQL `shared_blks_read` directly with physical disk I/O.
   It means pages loaded into shared buffers; some may have come from the
   operating-system page cache.
8. Do not treat a low TPS database as a low-load database. A small number of
   large scans can dominate read throughput.
9. Do not treat a granted `AccessExclusiveLock` as a wait. A lock wait exists
   only when another backend requests an incompatible lock and has not been
   granted it.
10. Conversely, do not treat an empty one-shot lock-wait item as proof that
    granted `AccessExclusiveLock` values are harmless. The waiter may appear
    before, after, or between snapshots.
11. Do not recommend dropping an index solely because `idx_scan = 0`.
12. Do not recommend global memory, durability, planner-cost, autovacuum, or
    WAL changes without showing the evidence, expected effect, risk, rollback
    plan, and validation method.
13. Do not recommend `UNLOGGED` for production data without an explicit
    durability and replication analysis.
14. Do not recommend a large global or role-level `work_mem` based only on temp
    I/O totals. Memory is potentially allocated per plan node, per parallel
    worker, and per concurrent query.
15. Do not recommend increasing `shared_buffers` merely because the workload
    reads a large volume of data. First determine whether the reads are useful,
    repeated, or avoidable.
16. Keep measurement periods separate. Do not calculate shares using counters
    whose `stats_since` or `stats_reset` periods differ unless the report
    contains comparable interval deltas.
17. Do not add metrics from non-overlapping database captures and present the
    result as a simultaneous cluster total.
18. Treat `empty`, `error`, and `unsupported` as different states:

    - `empty` often means that no matching event existed;
    - `error` means collection failed and creates an evidence gap;
    - `unsupported` means the capability was unavailable or not applicable.
19. All proposed production diagnostic SQL must be read-only. Mark queries
    that may still be expensive or may wait on relation locks.
20. Never hide uncertainty. A precise limitation is more useful than a false
    conclusion.

## Phase 1 — Inventory and validate all artifacts

Discover every relevant `*.json` file under `INPUT_PATHS` first. Also inventory
`*.html` files only to find reports that have no JSON companion. Do not select
only the newest report unless the input explicitly requests that. One-shot lock
captures and earlier captures may prove event repetition or contain the only
direct blocker/waiter relationship.

For each distinct artifact, record:

| Field | Required interpretation |
|---|---|
| Source filename | Exact path or basename |
| Artifact schema version | Validate that the structure is recognized |
| Generator | `pg_diag` name and version |
| Report target | Host/cluster and requested database, if present |
| PostgreSQL version | Include major/minor exactly as captured |
| Collection mode | Interval/multi-snapshot or one-shot |
| Start and end time | Preserve source timezone and normalize to UTC |
| Local time | Convert using `LOCAL_TIMEZONE` where useful |
| Sample count | State the number of snapshots where available |
| Sections/items | Total count and collection status distribution |
| Diagnostics | Artifact-level warnings and errors |
| Duplicate identity | Whether an HTML and JSON represent the same run |

Expected top-level artifact fields may include:

```text
artifact_schema_version
generator
content
report
runtime
display
query_texts
diagnostics
snapshots
snapshot_schemas
sections
items
```

Do not assume all versions populate every field. Inspect actual values.

Build a source registry before analyzing performance. It must make clear:

- which database each report actually queried;
- which items are database-local and which are cluster-wide;
- whether a title such as “Only DATABASE” agrees with the SQL scope;
- which observation windows overlap;
- which snapshots are isolated one-shot captures;
- which important collectors failed.

Calculate a collection status summary:

```text
ok count
empty count
error count
unsupported count
total items
(ok + empty) / total
```

Use this only as an inventory metric. Do not call `(ok + empty) / total` an
accuracy score. List high-impact missing items individually—for example,
failed table workload, index workload, query plans, lock diagnostics, buffer
cache, wait sampling, or kernel-level CPU accounting.

## Phase 2 — Establish time and counter semantics

Before calculating rates or shares, classify every used value:

| Type | How to use it |
|---|---|
| Instantaneous gauge | Valid only for the capture timestamp |
| One-shot row set | Proves only what existed at that moment |
| Interval delta | Difference over known endpoints; suitable for rates |
| Cumulative counter | Requires `stats_reset`/`stats_since` context |
| SQL statement total | Use the row’s own `stats_since` |
| Lifetime catalog statistic | Do not infer current rate without reset time |
| Sampled time series | Compare aligned timestamps and note missing samples |

For each interval:

1. identify exact start and end timestamps;
2. calculate duration from timestamps rather than assuming the nominal report
   duration;
3. verify that counters did not reset inside the window;
4. compute rates only from valid deltas;
5. preserve the original counter value and show the derived rate;
6. use consistent decimal/binary size units and state which convention is
   used;
7. use the captured PostgreSQL `block_size` if available; otherwise explicitly
   state the assumption before converting blocks to bytes.

When comparing separate artifacts:

- align by database, item, dimensions, and counter meaning;
- compare cumulative counters only if reset epochs are known and compatible;
- use two snapshots of replication error counters to identify new events;
- state whether windows are simultaneous, overlapping, or separated;
- do not imply cross-database causality from non-simultaneous windows.

## Phase 3 — Create an evidence ledger

Maintain an internal evidence ledger while analyzing. Every potential finding
must contain:

```text
Finding ID:
Priority candidate:
Database/cluster:
Observation window:
Affected component:
Evidence item IDs:
PIDs/queryids/relations/subscriptions:
Raw counters:
Derived values and formula:
Confidence: Confirmed | Strong attribution | Requires verification
User-visible impact:
Missing evidence:
Owner:
Proposed action:
Risk:
Rollback:
Validation metric:
```

Use item IDs and exact source values in the analysis even if the final prose
uses friendly titles. For all important arithmetic, recompute values from raw
counters. Examples include:

- bytes = blocks × captured block size;
- average rate = interval delta / exact seconds;
- statement frequency = calls / compatible accumulation duration;
- WAL per call = total WAL / calls from the same statement row and period;
- database share = database delta / sum of simultaneous compatible deltas.

Do not sum overlapping or nested SQL statements unless the source guarantees
that they are independent. A top-level stored procedure and SQL executed
inside it may represent the same work.

## Phase 4 — Analyze in the required order

The order below is intentional. It starts with collection quality and cluster
capacity, then identifies workload causes, then considers configuration.
Following this order prevents configuration tuning from masking avoidable SQL
or transaction-design problems.

### 4.1 Instance baseline and resource envelope

Establish:

- PostgreSQL version and primary/standby role;
- host virtualization and CPU topology;
- RAM and memory pressure;
- filesystem, mount, capacity, and used percentage;
- database sizes;
- active, idle, and idle-in-transaction connections versus limits;
- CPU user/system/iowait/steal where available;
- disk read/write throughput;
- disk utilization;
- disk request latency/await;
- database TPS and block deltas;
- checkpoint and archiver state.

Interpret these values together:

- High device utilization plus low latency usually indicates sustained
  throughput pressure, not necessarily a faulty disk.
- CPU headroom does not disprove a database bottleneck when backends wait on
  I/O or locks.
- Memory headroom does not prove that a larger PostgreSQL cache is the correct
  fix.
- A throughput peak aligned with iowait supports an I/O-pressure conclusion,
  but SQL attribution still requires query/database evidence.
- State whether storage type is known. Do not infer NVMe, SAN, local SSD, or
  RAID topology from a device name alone.

Conclude this subsection by explicitly answering:

1. Is the observed bottleneck CPU, memory, connections, storage latency,
   storage throughput, locks, SQL design, or not proven?
2. Which resources have headroom?
3. Which symptoms need workload attribution before capacity changes?

### 4.2 Collection health and observability

Review:

- item collection errors and timeout reasons;
- unavailable extensions such as `pg_stat_kcache`, `pg_wait_sampling`, or
  `pg_buffercache`;
- missing table/index workload items;
- exporter or collector queries visible in activity;
- sample gaps or failed snapshots;
- report item SQL scope versus the title and displayed database;
- whether expensive collector SQL uses `pg_relation_size()` over many
  relations;
- activated fallback items, their primary trigger, effective source, and
  changed result schema;
- whether machine summary reports `degraded: true` even when completeness is
  100% and `has_errors` is false;
- approximate `estimated_*` or `*_relpages` fields and any explicit selection
  truncation.

Explain how missing diagnostics constrain conclusions. Do not make the audit
depend on optional extensions when existing evidence already proves a major
problem.

A successful fallback is usable degraded evidence, not proof that the primary
collector succeeded. Preserve the primary timeout as a data-quality fact,
interpret fields using the effective fallback schema, and never look for the
primary schema merely because the artifact retains the parent `item_id`.
Distinguish an exact relation size from `relpages × block_size`; for partitioned
objects also determine whether only size was aggregated while workload counters
remained root-local.

### 4.3 Locks, blocking chains, and monitoring gaps

Inspect all lock-related items and all one-shot lock reports:

- lock mode counts grouped by `locktype`, `mode`, and `granted`;
- arrays or lists of holder PIDs and affected relations;
- blocked and blocking activity;
- `wait_event_type`, `wait_event`, query age, transaction age;
- `pg_blocking_pids()` results if captured;
- matching queryid, application name, user, database, and relation;
- transaction boundaries and scheduler/job identity;
- repeated appearances across snapshots.

Apply PostgreSQL lock compatibility, not intuition. In particular:

- `AccessExclusiveLock` conflicts with `AccessShareLock`;
- read-only metadata or size collectors can therefore wait behind application
  DDL, `TRUNCATE`, explicit `LOCK TABLE`, index changes, or other AEL holders;
- the number of granted AEL values does not equal the number of waiting
  sessions;
- an AEL on an index is still a relation lock;
- an empty wait snapshot only means no waiter was captured at that instant.

For every claimed blocking event, attempt to establish this chain:

```text
holder PID/queryid/application
  -> granted incompatible lock mode
  -> exact relation or transaction target
  -> waiter PID/queryid/application
  -> requested lock or Lock wait event
  -> measured wait duration
  -> exporter/job timeout or user-visible effect
```

If the artifacts show the chain only through the waiter, lock holder, and
relation, label the database blocking as **Confirmed**. If a Grafana or
Prometheus gap is part of `INCIDENT_CONTEXT`, explain:

- a blocked exporter collector can be the database-side blocker for metrics
  collection;
- if the wait exceeds the collector/statement/scrape deadline, the scrape may
  fail or lose a metric family;
- the report alone does not prove that every dashboard gap came from that
  lock;
- correlate each gap with exporter logs, Prometheus target logs, scrape
  duration, sample count, datasource health, and dashboard timestamps.

Recommend an explicit timeout chain:

```text
lock_timeout < statement_timeout < scrape_timeout
```

The exact values must be chosen from the real scrape interval and expected
collector runtime. Avoid inventing universal values.

Evaluate monitoring resilience:

- isolate expensive relation-size collectors from core health metrics;
- run expensive collectors less frequently;
- avoid `pg_relation_size()` for every relation/index on every scrape;
- expose collector-specific errors;
- keep one blocked collector from hiding all core metrics;
- alert on exporter `up`, scrape duration, scraped sample count, timeout and
  collector errors.

For application AEL holders, request inspection of:

- `TRUNCATE`;
- `ALTER TABLE` and other DDL;
- `CREATE/DROP/REINDEX`;
- explicit `LOCK TABLE`;
- dynamic SQL;
- called/nested routines;
- `pg_sleep`;
- scheduler overlap;
- transaction start/commit points.

Prefer architectural changes:

- calculate data outside the publication transaction;
- use staging/generation/double-buffer approaches;
- perform the final publish/swap in a short transaction;
- use a bounded `lock_timeout`;
- move sleep outside transactions;
- serialize overlapping jobs with a well-defined mechanism.

Do not prescribe a table swap blindly: dependency, foreign key, trigger,
privilege, publication, replication identity, and object identity behavior
must be verified.

### 4.4 Top SQL and workload attribution

Analyze SQL by at least:

- total execution elapsed time;
- calls;
- mean and maximum execution time;
- rows;
- shared blocks read and hit;
- temp blocks read and written;
- WAL bytes/records;
- database;
- user/role;
- application name where available;
- queryid;
- statement `stats_since`;
- interval activity and concurrency.

Separate these workload classes:

1. application OLTP;
2. monitoring/reporting;
3. scheduled procedures/batches;
4. archive/ETL/Spark/JDBC;
5. maintenance (`ANALYZE`, `VACUUM`, index operations);
6. replication workers;
7. exporter/diagnostic SQL.

For every major query, explain:

- normalized purpose inferred from SQL, without inventing business meaning;
- accumulation period;
- approximate completion frequency;
- volume per call where valid;
- whether several calls could overlap;
- read, temp, WAL, or lock signature;
- the plan evidence that is missing;
- the safest next measurement.

Never infer concurrency merely from `total_exec_time / wall-clock duration`.
The total can accumulate across calls and backends. Prove concurrency using
activity snapshots, overlapping timestamps, or scheduler history.

Never infer call interval using the wrong `stats_since`. Recalculate call
frequency carefully and distinguish:

- completed calls;
- currently active executions;
- scheduler launch frequency;
- overlapping executions.

For query optimization, request:

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, VERBOSE, FORMAT TEXT)
```

Run it only in an approved safe environment or for a safely bounded production
query. The audit itself must not execute a mutating or unexpectedly expensive
plan.

Look for:

- repeated identical calculations;
- overlapping identical work;
- non-sargable predicates;
- functions or casts applied to indexed columns;
- full scans for narrow time ranges;
- large exact `count(*)`;
- unnecessary sorts/hashes and temp spills;
- row-estimation errors;
- broad result sets;
- avoidable relation-size scans;
- full refresh patterns that could become incremental.

Recommend cache or single-flight behavior only with invalidation/freshness
requirements. Recommend materialized summaries only after defining ownership,
refresh cadence, failure behavior, and correctness tolerance.

### 4.5 Full scans, archive workloads, and exact counts

Treat sequential scans as evidence of access behavior, not automatically as a
problem. A sequential scan may be correct for:

- a small table;
- a query reading a large fraction of a table;
- maintenance;
- a one-time bulk load;
- an archive export.

Escalate when large relations are repeatedly scanned, especially for a narrow
date range or low output row count.

For archive/ETL/JDBC/Spark workloads, determine:

- source role and application;
- target tables;
- predicate shape;
- number of repeated scans;
- scanned versus returned rows;
- approximate bytes read;
- whether retries or multiple actions recompute the same DataFrame/query;
- whether a watermark is stored durably;
- whether the job reads only the newly arrived range.

For timestamp predicates, check sargability. A predicate such as:

```sql
editdate >= :from_timestamp
AND editdate < :to_timestamp
```

is generally easier to support than applying a function or cast to `editdate`.
Do not promise an index scan without a plan.

Evaluate in this order:

1. eliminate repeated execution;
2. use a durable incremental watermark;
3. make the predicate sargable;
4. check table clustering/correlation and data distribution;
5. test an existing or candidate B-tree index;
6. evaluate BRIN for naturally time-correlated large append-oriented data;
7. consider partitioning only with lifecycle, pruning, retention, and
   operational ownership defined.

For exact `count(*)` jobs:

- identify whether an exact live value is really required;
- consider planner/catalog estimates for approximate UI/monitoring;
- consider precomputed summary tables;
- consider asynchronous counting;
- consider incrementally maintained counters with correctness controls;
- prevent simultaneous counts of several very large tables.

State the consistency and staleness trade-off of every alternative.

### 4.6 Manual `ANALYZE` and maintenance workload

Identify manual `ANALYZE` statements, their table list, calls, frequency,
duration, and read volume. Determine:

- whether they run after actual data changes;
- whether a fixed table list is analyzed on a timer regardless of churn;
- whether scheduler frequency is shorter than useful statistics lifetime;
- whether autovacuum/analyze already covers the relations;
- whether column statistics targets are appropriate;
- whether the workload repeatedly reads large unchanged relations.

Prefer event-driven analysis after bulk changes or targeted analysis of changed
tables. Do not disable autovacuum or automatic analyze globally as a shortcut.

### 4.7 WAL, checkpoints, and mass rewrite patterns

Correlate:

- top SQL WAL generation;
- cluster/database interval WAL;
- calls and WAL per call;
- DML row deltas;
- dead tuples and vacuum activity;
- checkpoints;
- archiver backlog;
- physical/logical replication;
- scheduled full-refresh procedures.

Do not calculate a query’s percentage of cluster WAL from incompatible
accumulation periods. Prefer same-window deltas. If the attribution is based on
matching volumes rather than an exact shared interval, label it accordingly.

Investigate full-refresh procedures for:

- delete/reinsert or truncate/reload patterns;
- rewriting unchanged rows;
- repeated creation/drop of indexes or tables;
- staging inside the same long transaction;
- transaction-held AEL;
- large batches without generation reuse.

Possible redesigns include incremental refresh, generation tables, staging,
partition exchange-like designs where PostgreSQL semantics permit, or a short
publish phase. Every design must include failure recovery and rollback.

### 4.8 Autovacuum and churn

Review:

- dead/live tuple ratios and absolute counts;
- insert/update/delete interval deltas;
- autovacuum/analyze counts and timestamps;
- worker configuration;
- table-level reloptions;
- vacuum duration if available;
- WAL and rewrite patterns;
- wraparound/freeze risk;
- index bloat evidence where available.

Do not interpret a list of “autovacuum pressure” rows as a literal queue of the
same length. Determine whether workers are saturated using actual active worker
state and history.

Before increasing workers or cost limits, reduce avoidable churn. Then tune
large hot tables individually where evidence supports it. Include I/O impact,
worker memory, concurrency, and maintenance-window implications.

### 4.9 Index review

Create separate categories:

1. exact duplicate definitions;
2. indexes whose leading columns and predicates make another index potentially
   redundant;
3. constraint-backed indexes;
4. primary keys;
5. unique indexes;
6. replica identity indexes;
7. invalid indexes;
8. large indexes with no observed scans;
9. missing-index candidates supported by query plans.

For every removal candidate require:

- exact `pg_get_indexdef`;
- table and schema;
- size;
- `indisunique`, `indisprimary`, `indisvalid`, `indisreplident`;
- constraint and dependency checks;
- predicate and expression comparison;
- column order, sort direction, collation, opclass, and included columns;
- usage over a complete business cycle;
- known `stats_reset`;
- plan review for important SQL;
- write/WAL benefit estimate;
- saved recreation DDL;
- one-at-a-time rollout;
- rollback and regression monitoring.

`idx_scan = 0` means “not observed since an unknown or known reset,” not “safe
to remove.” Reports with failed index workload collection are insufficient for
deletion approval.

When reporting potential savings, separate:

- clearly identical indexes;
- probable duplicates requiring dependency validation;
- merely unused-looking indexes;
- hypothetical missing indexes.

Do not add all categories into a single guaranteed reclaim number.

### 4.10 Logical replication

Verify the real database scope first. PostgreSQL subscriptions are associated
with `pg_subscription.subdbid`. An item executed from one database may expose
cluster-wide subscription rows and mislabel them with `current_database()`.

For each subscription inspect:

- `subid` and `subname`;
- actual subscription database from `subdbid`;
- enabled state;
- main apply worker;
- parallel apply workers and leader PID;
- worker running state;
- latest message receipt time;
- received LSN;
- latest end LSN and time;
- receive/write/flush/apply lag where actually available;
- `apply_error_count`;
- `sync_error_count`;
- detailed conflict counters;
- counter `stats_reset`;
- table synchronization state;
- publisher-side slot state and retained WAL.

Apply these rules:

- A running main apply worker proves only that a worker is currently present.
- A zero receive gap or fresh message time does not prove zero apply lag.
- Historical error totals do not prove an active error rate.
- A positive delta between compatible captures proves new errors occurred.
- Error counters do not identify the failing relation or SQL; PostgreSQL logs
  and table sync state are required.
- `ALTER SUBSCRIPTION ... REFRESH PUBLICATION` is not a generic repair that
  automatically resynchronizes all existing subscribed tables.
- Never skip transactions, advance origins, drop slots, or reinitialize a
  subscription based only on this report.

For new errors, require:

1. exact timestamp and worker log;
2. subscription and actual database;
3. error/conflict type;
4. affected relation and key;
5. initial sync versus steady-state apply;
6. publisher/subscriber row reconciliation;
7. root cause, corrective action, and proof counters stopped increasing.

### 4.11 Physical replication, slots, and WAL retention

Review:

- standby sender/receiver state;
- sent/write/flush/replay LSNs;
- byte lag and time lag where available;
- sync/async state;
- replication slots;
- `restart_lsn` and `confirmed_flush_lsn`;
- retained WAL bytes;
- slot activity, invalidation reason, and safe WAL size;
- archiver failures and backlog.

Separate receive lag from replay/apply lag. A healthy physical standby does not
prove healthy logical subscriptions.

Never recommend deleting a slot solely because it retains WAL. Map it to its
consumer and document resynchronization consequences.

### 4.12 Configuration and operating system

Only review configuration after workload causes are described.

For each non-default or candidate setting, record:

- captured value;
- source (`default`, config file, role, database, client, session);
- affected scope;
- evidence that it contributes to the observed issue;
- expected improvement;
- memory/I/O/durability risk;
- restart requirement;
- rollback;
- before/after metric.

Explicitly review, where captured:

- `shared_buffers`;
- `effective_cache_size`;
- `work_mem`;
- `maintenance_work_mem`;
- `max_connections`;
- `random_page_cost` and `seq_page_cost`;
- autovacuum worker/cost/scale settings;
- checkpoint/WAL settings;
- `wal_recycle` and `wal_init_zero`;
- lock, statement, and idle transaction timeouts;
- huge pages.

Interpretation requirements:

- `effective_cache_size` is a planner estimate; it does not allocate memory.
- `work_mem` is not a per-connection cap.
- planner cost constants change plan choices; they do not accelerate storage.
- non-default WAL file behavior requires the original operational rationale
  and filesystem-specific testing.
- a session setting captured from a collector does not prove the cluster
  default. Inspect role/database settings separately.
- huge pages can reduce page-table overhead, but require OS capacity planning,
  restart preparation, and rollback. They are not a fix for repeated scans or
  lock contention.

## Phase 5 — Cross-correlate before assigning priority

Build causal narratives from independent items. Useful correlation patterns
include:

### Lock/observability narrative

```text
scheduled procedure
  -> long transaction
  -> granted AEL on relation/index
  -> exporter requests AccessShareLock
  -> exporter waits
  -> collector or scrape deadline expires
  -> missing Prometheus sample
  -> visible Grafana gap
```

Only the portion present in artifacts is confirmed. External log correlation
is required to complete the dashboard part.

### Read-pressure narrative

```text
large database block delta
  + high device read throughput/utilization
  + low TPS
  + one or more large full scans
  + matching application/database/time window
  -> strong attribution to analytical/archive scan workload
```

### Rewrite narrative

```text
scheduled full-refresh procedure
  + high WAL per run
  + large DML deltas
  + frequent autovacuum
  + AEL
  -> application refresh design creates write, vacuum, and lock pressure
```

### Replication narrative

```text
worker currently running
  + fresh receive position
  + error counter increased
  -> data is currently arriving, but apply correctness had failures
  -> logs and row reconciliation are mandatory
```

Use priority levels:

- **P0** — confirmed impact on availability/observability, active blocking, or
  dominant avoidable load requiring immediate containment and diagnosis.
- **P1** — confirmed performance/correctness issue requiring an implementation
  plan, dependency checks, or a longer observation period.
- **P2** — operational/configuration improvement that does not remove the
  demonstrated primary cause.

Do not use severity solely because a `pg_diag` item is colored or labelled
medium/high. Re-evaluate it in context.

## Phase 6 — Produce the final report

Write a comprehensive Markdown document to `OUTPUT_PATH`. Use
`OUTPUT_LANGUAGE`. Keep SQL identifiers, PostgreSQL terms, item IDs, settings,
queryids, PIDs, and application names unchanged.

The document must be understandable without opening the source reports. It
must be detailed enough that each team can create actionable tickets.

Use this exact high-level structure:

```markdown
# PostgreSQL Health and Performance Audit — <systems> — <date>

## Navigation

## Executive Summary
### How to Read Priorities and Confidence
### Who Should Start Work

## Sources, Observation Windows, and Limitations
### Terminology and Units

## Instance State

## P0. Locks and Monitoring/Data Gaps

## P0. High-Impact Scheduled Procedures, WAL, and Mass Rewrites

## P0/P1. Main Read and Temp-I/O Sources
### Primary/Operational Database
### Archive/Reporting Database
### Manual ANALYZE
### Periodic Exact Counts

## P1. Sequential Scans

## P1. Index Review

## P1. Autovacuum and Data Churn

## P1. Logical Replication
### Data Path and Scope
### Current State
### Changes Between Reports
### Physical Replication and Slots
### Required Checks

## P2. Configuration and Operating System
### Huge Pages
### Settings That Must Not Be Changed Automatically

## Observability Improvements

## Work Plan, Owners, and Acceptance Criteria
### Within 0–2 Days
### Within 1–2 Weeks
### After Stabilization

## Read-Only Verification Queries

## Corrected Claims and Remaining Uncertainties
```

If a section has no supporting artifact, keep it short and explicitly say
“not established from the supplied captures.” Do not manufacture content to
fill the template.

### Required content of the Executive Summary

The executive summary must:

1. state the main system limitation observed in the window;
2. state which common bottlenecks were not observed;
3. list the top problems in priority order;
4. distinguish SCPRD-like operational workload from SCPRDARC-like archive
   workload when applicable;
5. mention lock impact on monitoring when proven;
6. mention logical replication correctness risk when counters increased;
7. list dangerous or unsupported “quick fixes” that should not be applied;
8. remain concise enough to read in approximately two minutes.

Include a priority table:

| Priority | Problem | Confidence | Impact | Owner | First action |
|---|---|---|---|---|---|

Include an owner table:

| Team/owner | First task | Why it belongs to them | Required evidence |
|---|---|---|---|

### Required content of each finding

For each material finding use this order:

1. **Evidence** — exact window, database, item, PID/queryid/relation, and
   counters.
2. **Interpretation** — what the values mean in PostgreSQL terms.
3. **Impact** — application, monitoring, I/O, WAL, vacuum, storage, or data
   correctness consequence.
4. **Confidence** — confirmed, strong attribution, or requires verification.
5. **What to check** — missing plans, logs, routine definitions, scheduler
   history, dependencies, reset timestamps, or table state.
6. **What to change** — concrete change candidates, ordered from least risky to
   architectural.
7. **Risk and rollback** — what can break and how to revert.
8. **Acceptance criteria** — measurable result in a comparable window.

Avoid vague actions such as “optimize the query,” “check the database,” or
“increase resources.” Name the exact queryid, routine, role, table,
subscription, metric, or collector and the evidence required.

### Required source and limitation table

Include:

| Artifact | Target | Mode | UTC window | Local window | Samples | Item status | Important gaps |
|---|---|---|---|---|---:|---|---|

Explicitly state:

- whether windows overlap;
- whether counters have known reset epochs;
- which important items failed;
- which optional extensions were unavailable;
- whether execution plans and routine bodies are absent;
- whether any report item has incorrect database scope.

### Required instance table

Include:

| Metric | Observation | Interpretation | Action |
|---|---:|---|---|

Cover CPU, RAM, connections, filesystem capacity, database size, I/O
throughput/utilization/latency, TPS, database block deltas, checkpoints, and
archiver where available.

### Required workload tables

For major SQL:

| Database | Role/app | Queryid | Calls/active copies | Mean/max elapsed | Shared read | Temp I/O | WAL | Period | Interpretation |
|---|---|---:|---:|---:|---:|---:|---:|---|---|

For scans:

| Database | Relation | Size | Scan pattern | Repetition | Estimated read volume | Query/app | Confidence |
|---|---|---:|---|---:|---:|---|---|

For lock incidents:

| Time | Holder PID/queryid | Lock/relation | Waiter PID/queryid | Wait duration | User impact | Confidence |
|---|---|---|---|---:|---|---|

For replication:

| Database | Subscription | Worker state | Receive state | Error delta | Conflict delta | Apply lag known? | Required action |
|---|---|---|---|---|---|---|---|

### Required work plan

Every action row must have:

| Timeframe | Priority | Owner | Exact action | Evidence to collect | Acceptance criterion | Rollback/guardrail |
|---|---|---|---|---|---|---|

Recommended timeframes:

- **0–2 days** — correlate incidents, collect plans/logs, add guardrails,
  identify owners, contain repeat scans or exporter timeouts.
- **1–2 weeks** — deploy query/transaction/job fixes, first safe index cleanup,
  replication reconciliation.
- **After stabilization** — repeat comparable captures, then evaluate capacity
  and configuration changes.

Each task must produce:

- source queryid/PID/relation/subscription;
- before evidence;
- one clearly described change;
- after evidence over a comparable period;
- rollback plan;
- owner and recheck date.

Do not propose changing SQL, indexes, memory settings, and storage at the same
time for the same workload. The team must be able to attribute improvement or
regression to a controlled change.

### Required acceptance metrics

Use concrete metrics where applicable:

- no monitoring scrape gaps caused by database locks;
- exporter waits remain below its lock timeout;
- AEL duration no longer reaches tens of seconds;
- fewer repeated full scans;
- reduced database interval block reads;
- reduced device read throughput/utilization during the same workload;
- reduced shared reads and temp blocks per SQL call;
- lower WAL per batch cycle;
- reduced autovacuum churn after eliminating rewrites;
- no growth in logical replication error counters;
- table reconciliation succeeds;
- no plan or latency regression after index changes.

Avoid arbitrary percentage targets unless a service objective or baseline
supports them.

## Phase 7 — Add safe read-only verification SQL

Add only the queries relevant to unresolved findings. Explain what each query
proves, where it must be run, required privileges, and caveats.

At minimum consider templates for:

1. current blockers and waiters using `pg_blocking_pids()`;
2. relation locks held by a confirmed PID;
3. definitions and dependencies of suspect routines;
4. `pg_cron` schedule and execution history;
5. actual database of logical subscriptions via `subdbid`;
6. logical replication conflict counters and `stats_reset`;
7. table synchronization state from `pg_subscription_rel`;
8. publisher-side replication slots and retained WAL;
9. complete index candidate metadata and dependencies;
10. role/database settings from `pg_db_role_setting`.

Safety notes:

- Even read-only catalog queries can be expensive on a large cluster.
- `pg_relation_size()` can request relation locks and wait behind AEL.
- Limit relation enumeration and use an agreed session `lock_timeout`.
- A current lock query cannot reconstruct a completed incident; logs or
  high-frequency samples are required.
- `EXPLAIN ANALYZE` executes the statement and is not automatically safe.

## Phase 8 — Final fact-check

Before writing the final file, audit every important sentence:

### Numbers

- Recalculate conversions and rates.
- Check decimal versus binary units.
- Check query-specific accumulation periods.
- Check interval endpoints and duration.
- Check that percentages use compatible denominators.
- Check that totals do not double-count nested SQL.

### Causality

- Does the evidence identify the same database, timestamp, PID/queryid, and
  relation?
- Is the conclusion direct or inferred?
- Does an empty snapshot contradict the claim, or merely fail to observe the
  event?
- Is a dashboard symptom supported by monitoring logs or only by a plausible
  database-side mechanism?

### PostgreSQL semantics

- Elapsed time is not CPU time.
- Shared reads are not identical to physical reads.
- Granted locks are not waits.
- Running logical workers do not prove zero apply lag.
- Receive position does not prove apply correctness.
- Historical counters are not current rates.
- Zero index scans do not authorize deletion.
- Session/client settings are not automatically cluster defaults.
- `REFRESH PUBLICATION` is not universal data repair.

### Recommendations

- Is the owner named?
- Is the first diagnostic step specific?
- Is a plan or log required before a risky change?
- Is production risk stated?
- Is rollback possible?
- Is the acceptance criterion measurable?
- Does the change address the proven cause rather than only a symptom?

### Completeness

- All input artifacts were inventoried.
- All collection errors affecting conclusions were disclosed.
- Operational and archive databases were analyzed separately.
- Locks, main SQL, scans, exact counts, manual maintenance, WAL, autovacuum,
  indexes, logical replication, physical replication, and configuration were
  considered.
- Unsupported quick fixes were explicitly rejected.
- Remaining unknowns are visible.

## Quality bar for the final answer

The audit is complete only when:

1. a developer can identify the exact routine/query to inspect;
2. a DBA can identify the exact lock, index, vacuum, or setting evidence;
3. monitoring engineers can determine whether a gap occurred at the database,
   exporter, Prometheus, datasource, or dashboard layer;
4. replication owners can distinguish worker liveness, receive progress,
   apply progress, errors, conflicts, and data correctness;
5. every P0/P1 item has an owner, next action, evidence request, guardrail, and
   acceptance criterion;
6. every strong claim is traceable to a source artifact and compatible
   observation period;
7. no unsafe production change is presented as certain based on a short
   diagnostic capture.

Write the completed Markdown report to `OUTPUT_PATH`. Do not overwrite or
modify the source artifacts.
