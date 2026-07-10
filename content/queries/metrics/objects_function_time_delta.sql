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
  round(total_time::numeric, 3) as total_time_ms,
  round(self_time::numeric, 3) as self_time_ms
from pg_stat_user_functions
order by total_time desc nulls last, schemaname, funcname
limit 100
