select
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.queryid::text as query_id,
  s.calls::int8 as calls,
  round(s.mean_exec_time::numeric, 3) as mean_exec_time_ms,
  round(s.total_exec_time::numeric, 3) as total_exec_time_ms,
  round(s.max_exec_time::numeric, 3) as max_exec_time_ms,
  s.rows::int8 as rows,
  s.shared_blks_read::int8 as shared_blks_read,
  s.temp_blks_read::int8 as temp_blks_read,
  s.temp_blks_written::int8 as temp_blks_written,
  s.wal_bytes::numeric as wal_bytes,
  left(coalesce(s.query, '<query text unavailable>'), 4000) as query
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database()
order by s.mean_exec_time desc nulls last
limit 50
