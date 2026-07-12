# Database Session Outcomes Delta

This instruction belongs to report item `snapshot_delta_workload.database_session_outcomes_delta`.

## What this item shows
- Sessions created, abandoned, killed, or terminated by fatal errors per database during the window.
- Accumulated session, active, and idle-in-transaction milliseconds.

## What to watch
- Abandoned or fatal sessions, rapid connection churn, and disproportionate idle-in-transaction time.

## Automatic evaluation
- New abandoned or fatal sessions produce `medium` severity.
- Operator-killed sessions are reported but not automatically treated as a fault.

## Interval coverage
- Values require matching database OID and unchanged `pg_stat_database.stats_reset`.

## Common fault causes
- Network loss, client crashes, server errors, pool churn, and missing transaction boundaries.

## Checklist
- Correlate abnormal outcomes with PostgreSQL, pooler, application, and network logs.
- Compare session creation with connection pressure and sessions-by-state charts.
