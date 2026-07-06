select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.queryid::text as query_id,
  s.calls::int8 as calls,
  round(s.total_exec_time::numeric, 3) as total_exec_time_ms,
  s.rows::int8 as rows,
  left(coalesce(s.query, '<query text unavailable>'), 4000) as query
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database()
order by s.total_exec_time desc nulls last
limit 50
