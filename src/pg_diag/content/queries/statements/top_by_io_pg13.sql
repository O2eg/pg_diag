select
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.dbid,
  s.userid,
  null::boolean as toplevel,
  s.queryid::text as query_id,
  case when s.queryid is null then 'statistics_only' else 'full' end as identity_visibility,
  s.calls::int8 as calls,
  (s.shared_blks_read + s.shared_blks_written)::int8 as shared_io_blks,
  s.shared_blks_hit::int8 as shared_blks_hit,
  s.shared_blks_read::int8 as shared_blks_read,
  s.shared_blks_dirtied::int8 as shared_blks_dirtied,
  s.shared_blks_written::int8 as shared_blks_written,
  ((s.shared_blks_read + s.shared_blks_written)::numeric * current_setting('block_size')::int)
    as shared_io_bytes,
  s.blk_read_time::numeric as blk_read_time_ms,
  s.blk_write_time::numeric as blk_write_time_ms,
  s.total_exec_time::numeric as total_exec_time_ms,
  s.rows::int8 as rows,
  left(coalesce(s.query, '<query text unavailable>'), 4000) as query,
  case when s.queryid is null then 'unknown' else 'ok' end as pg_diag_internal_severity,
  case when s.queryid is null then 'Query ID and SQL text are hidden for this statement owner' else '' end
    as pg_diag_internal_reason
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database()
order by (s.shared_blks_read + s.shared_blks_written) desc nulls last
limit 50
