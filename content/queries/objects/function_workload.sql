select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  s.funcid,
  s.schemaname,
  s.funcname,
  pg_get_function_identity_arguments(s.funcid) as function_signature,
  current_setting('track_functions') as track_functions,
  db.stats_reset,
  s.calls::int8 as calls,
  round(s.total_time::numeric, 3) as total_time_ms,
  round(s.self_time::numeric, 3) as self_time_ms
from pg_stat_user_functions s
left join pg_stat_database db on db.datname = current_database()
order by s.total_time desc nulls last, s.schemaname, s.funcname, s.funcid
limit 100
