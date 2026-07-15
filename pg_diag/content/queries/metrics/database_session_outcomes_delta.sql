select
  statement_timestamp() as snapshot_time,
  datid,
  datname,
  stats_reset,
  sessions::int8 as sessions,
  sessions_abandoned::int8 as sessions_abandoned,
  sessions_fatal::int8 as sessions_fatal,
  sessions_killed::int8 as sessions_killed,
  (session_time::numeric) as session_time_ms,
  (active_time::numeric) as active_time_ms,
  (idle_in_transaction_time::numeric) as idle_in_transaction_time_ms
from pg_catalog.pg_stat_database
where datname is not null
order by sessions desc nulls last, datname
