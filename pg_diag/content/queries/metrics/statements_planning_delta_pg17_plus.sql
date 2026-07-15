select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.dbid,
  s.userid,
  s.toplevel,
  (select stats_reset from pg_stat_statements_info) as global_stats_reset,
  s.stats_since as entry_stats_since,
  current_setting('pg_stat_statements.track_planning') as track_planning,
  s.queryid::text as query_id,
  s.plans::int8 as plans,
  (s.total_plan_time::numeric) as total_plan_time_ms,
  ''::text as query
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database() and s.queryid is not null
order by s.total_plan_time desc nulls last
limit 50
