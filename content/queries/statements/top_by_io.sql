select
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.queryid::text as query_id,
  s.calls::int8 as calls,
  (s.shared_blks_read + s.shared_blks_written)::int8 as shared_io_blks,
  s.shared_blks_hit::int8 as shared_blks_hit,
  s.shared_blks_read::int8 as shared_blks_read,
  s.shared_blks_dirtied::int8 as shared_blks_dirtied,
  s.shared_blks_written::int8 as shared_blks_written,
  round(s.blk_read_time::numeric, 3) as blk_read_time_ms,
  round(s.blk_write_time::numeric, 3) as blk_write_time_ms,
  round(s.total_exec_time::numeric, 3) as total_exec_time_ms,
  s.rows::int8 as rows,
  left(coalesce(s.query, '<query text unavailable>'), 4000) as query
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database()
order by (s.shared_blks_read + s.shared_blks_written) desc nulls last
limit 50
