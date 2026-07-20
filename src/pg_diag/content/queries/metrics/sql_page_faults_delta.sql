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
  k.exec_minflts::int8 as exec_minflts,
  k.exec_majflts::int8 as exec_majflts,
  (k.exec_minflts + k.exec_majflts)::int8 as exec_page_faults,
  s.query as query
from pg_stat_kcache() k
join pg_stat_statements s
  on s.dbid = k.dbid and s.userid = k.userid and s.queryid = k.queryid
join pg_database d on d.oid = k.dbid
left join pg_roles r on r.oid = k.userid
where d.datname = current_database() and k.top is true
order by k.exec_majflts desc nulls last, k.exec_minflts desc nulls last
limit 250
