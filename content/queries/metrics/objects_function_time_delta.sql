select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  schemaname,
  funcname,
  calls::int8 as calls,
  round(total_time::numeric, 3) as total_time_ms,
  round(self_time::numeric, 3) as self_time_ms
from pg_stat_user_functions
order by total_time desc nulls last, schemaname, funcname
limit 100
