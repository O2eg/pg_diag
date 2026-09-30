# CSV log parser regression coverage

The September 2026 offline replay exposed gaps between per-item recall and event
classification. Tests use synthetic CSV records; production logs are not fixtures.

| Input variant | Owning item and meaning |
|---|---|
| `terminating walsender process due to replication timeout` | Replication: `walsender_timeout`, including LOG severity |
| `unexpected EOF on standby connection` | Replication: `standby_disconnect` |
| `unexpected EOF on client connection with an open transaction` | Query termination: `client_disconnect_open_transaction`, including LOG/08006 |
| `automatic aggressive vacuum of table` | Autovacuum and maintenance |
| `duration: ... ms parse/bind ...` | Query resources: separate `parse_duration` / `bind_duration` stages |
| `duration: ... ms` without SQL | Query resources: `duration_only`, no invented SQL attribution |
| Background worker exits with nonzero code | Lifecycle: `background_worker_exit`, not evidence of a postmaster crash |
| `process ... detected deadlock while waiting for ...` | Lock waits: supplemental `deadlock_detected`, not another SQLSTATE 40P01 incident |

Recall must work with only the owning item selected. Duration stages, worker PIDs,
lock targets and transaction-disconnect timestamps must survive RLE without loss.
Auto-explain duration records must not add query execution counts.

The deadlock summary and graph count all repeats before the table cap. Event and
series counts are separate; output omission metadata must not be confused with
scan coverage. Error chronology severity includes events hidden by its row cap.
The plan reference count budget accommodates every displayed chart point, while
the independent 64 MiB byte budget remains enforced.

Regression checks live in `test_logscan_phase.py`, `test_server_log_items.py`,
`test_logscan_core.py`, and `diagnostic_graph_regressions.test.js`.

For a large local replay, record the source directory, exact CSV-clock window,
timezone, selected items and output paths, plus depth, scan, return, probe,
verification and wall-clock limits. Compare against an independent streaming CSV
count over the exact time window. Preserve baseline artifacts. Scan bounds rounded
to a second may include records subsequently excluded by the precise window filter.
The collection limits and 100/200-row, 2000-point presentation limits are distinct;
a successful schema check alone does not establish semantic completeness.


## SQL links from log events

Log SQL stays bounded to 2000 characters (`LINE_CAP`); hover previews use at
most 300 characters. A truncated retained SQL text is explicitly marked when
opened. Never expand these limits to retain megabyte-size statements by default.

`artifact.query_texts` is the shared text dictionary, keyed by the PostgreSQL ID
when nonzero, otherwise the first 20 hex characters of the SHA256 hash of the
retained sanitized SQL, without a prefix.
The same key is displayed in Query ID. Signed 64-bit IDs remain strings.
Insertion checks key presence: the first text wins, even if later variants are
longer. Different SQL texts for one ID set `representative_sample` metadata;
truncation metadata describes the stored sample, not a discarded later variant.
Grouped rows deduplicate by this key. A record without SQL can reuse an existing
catalog sample for its ID; an unknown ID stays plain text. Query resource tables
have no separate Query sample column.

Table `result.query_links.query_id` is aligned with original row indexes; values
are one reference or a list of references for a grouped row. Sorting and filtering
retain this association. Transient source `query_ref` columns are removed during
artifact assembly. Charts reference the same dictionary through `tooltip.query_ref`;
legacy per-chart query references still render. No SQL is copied into these links.
`query_text_metadata` records truncation of catalog entries.

Chronology, deadlocks, lock waits, resource/maintenance events, grouped errors and
warnings, replication, lifecycle, system/crash events and other log tables expose
links when their records carry SQL. Checkpoints, routine autovacuum, archiving,
authentication and inventory usually have no application query to show. A single
error fingerprint can expose multiple query links without changing its frequency.
Termination chart clicks open SQL; auto_explain retains plan clicks and provides
Show query in the plan dialog. The SQL field, logged statement/execute/parse/bind
duration and auto_explain Query Text are supported sources of retained SQL.


## Count completeness in HTML

The renderer hides `count_complete` columns for all parsed server-log items;
row flags and result metadata remain in JSON. One warning above each affected
result replaces the technical column when a row or result has
`count_complete=false`, or the shared log window has `ranking_complete=false`
or `window_truncated=true`. Empty results and log charts receive the same
warning. Display row/point limits alone do not trigger it. The log file inventory
is not parsed-event data and is excluded, as are unrelated SQL items. Existing
per-item diagnosis and detailed coverage notes remain available.


The replication events table presents the query catalog reference as a
`Replication command` text column, not a Query ID link. It shows the entire
retained command without the six-line cell collapse. Sorting, filtering and
both formatted/raw table exports use command text. JSON references and the
shared bounded SQL catalog are retained without duplicating SQL per row.


## Log table column order

HTML uses per-item priority lists in `LOG_TABLE_COLUMN_ORDER`. For tables with
Query ID, compact time/severity or impact columns come first and SQL moves to
positions 3–5 for the current schemas. Optional columns are skipped; unknown
columns retain their relative order at the end. A fallback keeps Query ID in
positions 3–7 whenever at least three columns exist. Tables without Query ID
keep their order. Replication retains its inline command presentation.

The renderer reorders column descriptors, not JSON rows or source indexes.
References, filtering, sorting and exports therefore use the same original
cells. Table exports follow the visible order, while the saved JSON is unchanged.


## Log chart time axes

Log charts label ticks with local calendar date and time and bound the axis by
displayed events, with a 30-second margin for edge bars. Auto-explain collection
no longer adds zero-valued boundary points or reserves point budget for them.
The renderer also excludes legacy zero anchors and null padding from log charts,
while preserving real zero-duration events with tooltip/plan metadata. Other
charts retain their existing time-axis behavior. Point-limit warnings remain:
the last displayed event is not necessarily the last event in the source logs.


## Auto-explain duration-based eviction

The 2000-point limit retains the slowest executions across the whole log window,
using a bounded dictionary keyed by SQL identity plus execution sequence and a
min-heap of durations. Ties preserve earlier input events. Multiple executions
of the same SQL remain distinct, so their timings and plans are not overwritten.
The selected events are then grouped into clock-aligned time buckets (one minute
by default, configurable with `settings.bucket_seconds`), each displaying at most
15 slowest retained executions. Global eviction and per-bucket omissions are
reported separately.

The shared SQL catalog remains available to all items. Only displayed plans are
interned, slowest first, under the independent plan byte budget. Total, parsed,
complete and duration-band counts still cover all collected executions, including
evicted ones. Item summaries always state total/retained/evicted counts and the
duration selection policy. Intentional selection is distinct from incomplete
scan/parse/reference evidence.

Regression tests cover late heavy plans, repeated SQL, equal and zero durations,
dense and configurable buckets, totals after eviction, and reference budget
priority. The local replay must compare global selection against an independent
top-2000 sort of all source auto-explain events, then apply the 15-execution
per-bucket limit when checking the displayed duration multiset.


## SQL masking and connection classifications

Generic `key` is not a credential marker: JOIN/WHERE identifiers such as
`orderkey`, `storerkey`, `keyword_id` and plan fields such as `Sort Key` must
survive unchanged. Explicit password/token/secret/credential names and
api/access/private/encryption/signing/auth/client keys remain redacted, as do
credential literals, URI passwords, authorization values and AWS access keys.
SQL sample caps remain unchanged.

SQLSTATE 55P03 with a lock-timeout message is `lock_timeout`, not NOWAIT.
Generic client send/receive failures are routed using backend_type: walsender
to replication, client backend to query termination, missing backend type to
an explicitly unclassified connection-disconnect category. Recall for an
individually selected item and both RLE layers must preserve these events and
their timestamps, including identical disconnects in different minutes.
