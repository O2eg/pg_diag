# Maximizing Report Coverage: Server Configuration

`pg_diag` degrades gracefully: every item that cannot find its data source is
reported as `empty` or `unsupported` with a reason instead of failing the run.
This guide is the reverse view — what to enable on the PostgreSQL server so
the report carries the maximum amount of evidence. Every setting here is
observability-only; none of them change query behavior.

Accounts and network access are a separate concern:
[access-best-practices.md](access-best-practices.md) covers the least-privilege
`pgdiag` database role (including grants for the extensions below), the
dedicated SSH account, filesystem permissions for server-log access, and every
supported connection pattern (direct TLS, SSH, jump hosts, local sockets,
Patroni/HAProxy).

## Table of contents

- [Quick reference](#quick-reference)
- [Diagnostic extensions](#diagnostic-extensions)
- [Statistics parameters](#statistics-parameters)
- [Server log parameters](#server-log-parameters)
- [Overhead notes](#overhead-notes)
- [Accounts, SSH, and connection methods](#accounts-ssh-and-connection-methods)

## Quick reference

`postgresql.conf` (settings marked *restart* need a server restart, the rest
apply on reload):

```ini
# --- extensions (restart) ---
shared_preload_libraries = 'pg_stat_statements,pg_stat_kcache,pg_wait_sampling'
pg_stat_statements.max = 5000
pg_stat_statements.track = all
pg_stat_statements.track_utility = on

# --- statistics (track_activity_query_size: restart) ---
track_io_timing = on
compute_query_id = auto
track_activity_query_size = 32768
track_functions = pl

# --- server log (logging_collector: restart) ---
logging_collector = on
log_destination = 'stderr,csvlog'
log_directory = '/var/log/postgresql'
log_file_mode = 0640
log_rotation_age = 1d
log_rotation_size = 100MB
lc_messages = 'C'
log_checkpoints = on
log_autovacuum_min_duration = 0
log_lock_waits = on
log_temp_files = 0
```

In every database that should be covered by the report:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_stat_kcache;
CREATE EXTENSION IF NOT EXISTS pg_wait_sampling;
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
```

Then apply the reference `pgdiag` grant set from
[access-best-practices.md](access-best-practices.md#dedicated-postgresql-role)
so the diagnostics role can read the new views.

## Diagnostic extensions

| Extension | Preload | What the report gains |
|---|---|---|
| `pg_stat_statements` | yes | The whole `statements` section (top queries by time, I/O, WAL, temp), per-query snapshot charts, and the query-text catalog behind clickable query ids across the report |
| `pg_stat_kcache` | yes, listed **after** `pg_stat_statements` | Kernel-level truth per query: real disk reads vs page cache, user/system CPU; metric charts (`database_kernel_cpu_rate`, filesystem I/O and context-switch deltas) |
| `pg_wait_sampling` | yes | The `wait_profile` section: sampled wait-event profile over time instead of the single-moment `pg_stat_activity` view |
| `pg_buffercache` | no | The `buffer_cache` section: shared_buffers utilization, usage-count distribution, top cached and dirty relations |

Notes:

- All four are read-only observers. `pg_stat_statements`,
  `pg_wait_sampling`, and `pg_stat_kcache` must be in
  `shared_preload_libraries` (restart); `pg_buffercache` needs only
  `CREATE EXTENSION`.
- `pg_stat_statements.track = all` includes statements inside functions;
  `pg_stat_statements.track_planning = on` adds planning-time columns but has
  a measurable cost on high-QPS clusters — enable deliberately.
- Missing extensions do not break the run: the affected items report
  `unsupported` with the missing capability named.
- `auto_explain` (preload-only library) writes plans of slow queries to the
  server log. `server_log.auto_explain_plans` reconstructs multiline csvlog
  records and recognizes text/JSON/XML/YAML plans. The chart keeps the ten
  longest queries per clock-aligned minute; tooltips contain a sanitized query
  sample capped at 300 characters. Clicking a block opens its collector-
  sanitized, bounded plan in the self-contained report's read-only viewer;
  original unsanitized log text is never retained in the artifact.

## Statistics parameters

| Parameter | Value | What the report gains |
|---|---|---|
| `track_io_timing` | `on` | Read/write **time** (not just counts) in `pg_stat_statements`, `pg_stat_database`, and the I/O snapshot charts; without it latency attribution is guesswork |
| `compute_query_id` | `auto` (PG14+) | `query_id` in `pg_stat_activity`, csvlog, and EXPLAIN — this is what links activity, locks, and server-log items to the query texts collected from `pg_stat_statements` |
| `track_activity_query_size` | `32768` (restart) | Full statement texts in activity and lock items instead of texts cut at 1024 bytes |
| `track_functions` | `pl` | Per-function call statistics consumed by the function workload items |

Verify `track_io_timing` cost with `pg_test_timing` on exotic virtualized
clocks; on typical hardware it is negligible.

## Server log parameters

These feed the `server_log` report section
(`--log-depth-time-min`, see the README section "Collect Server Logs"). The
filesystem side — ACLs on the log directory, the `log_file_mode` interaction —
is documented in
[access-best-practices.md](access-best-practices.md#server-log-access-optional).

| Parameter | Value | Items it lights up |
|---|---|---|
| `logging_collector` | `on` (restart) | The whole section: csvlog files exist |
| `log_destination` | contains `csvlog` | Same |
| `log_directory` | outside PGDATA | Cleaner permissions story for the collector account |
| `log_file_mode` | `0640` | Required for the documented ACL recipe to survive rotation |
| `log_rotation_age` / `log_rotation_size` | `1d` / `100MB` | Bounded files; `log_files_overview` flags disabled rotation as a finding |
| `lc_messages` | `C`, `POSIX`, or `en_*` recommended | Enables all content items. With another locale, SQLSTATE-driven authentication failures/deadlocks remain complete; query termination and system incidents report structured-only partial coverage; the file overview remains complete; localized-message items report `unsupported`. |
| `log_checkpoints` | `on` (default since PG15) | `checkpoints`: trigger reason, buffers, write/sync timings |
| `log_autovacuum_min_duration` | workload-specific ms threshold | `autovacuum_runs` chronology and `maintenance_events`; the latter emits only failures/emergencies/lock waits or successful runs crossing its documented 5 s / 128 MiB / 64 MiB thresholds |
| `log_lock_waits` | `on` | Lock-wait history from the log (waits longer than `deadlock_timeout`); also enriches the error chronology |
| `auto_explain.log_min_duration` | workload-specific threshold | `auto_explain_plans`: ten longest logged queries per minute |
| `auto_explain.log_format` | `json` recommended | Machine-readable plan validation; text, XML, and YAML are also recognized |
| `auto_explain.log_parameter_max_length` | `0` | Avoid logging bind-parameter values alongside plans |
| `log_min_duration_statement` | workload-specific ms threshold | Duration groups in `query_resource_events`; avoid `0` on high-QPS production systems |
| `log_temp_files` | workload-specific KiB threshold | Temporary-file groups and total/max spill bytes in `query_resource_events` |
| `log_connections` / `log_disconnections` | optional | Connection-churn evidence; high volume — enable deliberately |

Errors, FATAL/PANIC events, deadlocks (`deadlock detected`), authentication
failures, WAL archiver failures, and wraparound warnings are logged
unconditionally — the corresponding items work with any of the above as long
as csvlog itself is enabled.

## Overhead notes

- Everything in this guide is read-only instrumentation; the notable costs
  are `pg_stat_statements.track_planning` (per-statement timing on hot paths),
  `track_io_timing` on systems with slow clock sources, and
  `log_connections`/`log_disconnections` log volume on connection-heavy
  applications without a pooler.
- Restart-class settings: `shared_preload_libraries`,
  `track_activity_query_size`, `logging_collector`.
- After changing `shared_preload_libraries`, run the `CREATE EXTENSION`
  statements per database; preload alone exposes no views.

## Accounts, SSH, and connection methods

All account and transport setup lives in
[access-best-practices.md](access-best-practices.md):

- [Dedicated PostgreSQL role](access-best-practices.md#dedicated-postgresql-role) —
  the `pgdiag` reference grant set, including conditional grants for the
  extension views above;
- [Dedicated SSH account](access-best-practices.md#dedicated-ssh-account) —
  the non-root `pg_diag_ssh` account for `remote` mode (shell-capable for
  server-log collection);
- [Server log access](access-best-practices.md#server-log-access-optional) —
  filesystem ACLs for the log directory and what NOT to grant in the database;
- [Recommended connection patterns](access-best-practices.md#recommended-connection-patterns) —
  direct TLS, full SSH, jump hosts, local peer-auth sockets, and the patterns
  to avoid;
- [Patroni and HAProxy](access-best-practices.md#patroni-and-haproxy) —
  topology-aware collection in HA clusters.
