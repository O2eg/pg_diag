select
  statement_timestamp() as snapshot_time,
  (select oid from pg_database where datname = current_database()) as datid,
  current_database() as datname,
  funcid,
  schemaname,
  funcname,
  (select stats_reset from pg_stat_database where datname = current_database())
    as database_stats_reset,
  calls::int8 as calls,
  (total_time::numeric) as total_time_ms,
  (self_time::numeric) as self_time_ms
from pg_stat_user_functions
order by total_time desc nulls last, schemaname, funcname
limit 100
