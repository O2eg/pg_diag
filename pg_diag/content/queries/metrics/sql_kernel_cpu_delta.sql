select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, k.userid::text) as rolname,
  k.dbid,
  k.userid,
  k.top as toplevel,
  k.stats_since as kcache_stats_since,
  k.queryid::text as query_id,
  s.calls::int8 as calls,
  k.exec_user_time::numeric as exec_user_time,
  k.exec_system_time::numeric as exec_system_time,
  (k.exec_user_time + k.exec_system_time)::numeric as exec_cpu_time,
  s.query as query
from pg_stat_kcache() k
join pg_stat_statements s
  on s.dbid = k.dbid and s.userid = k.userid and s.queryid = k.queryid
join pg_database d on d.oid = k.dbid
left join pg_roles r on r.oid = k.userid
where d.datname = current_database() and k.top is true
order by (k.exec_user_time + k.exec_system_time) desc nulls last
limit 250
