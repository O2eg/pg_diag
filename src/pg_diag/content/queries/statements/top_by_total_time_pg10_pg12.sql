select
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.dbid,
  s.userid,
  null::boolean as toplevel,
  s.queryid::text as query_id,
  case when s.queryid is null then 'statistics_only' else 'full' end as identity_visibility,
  s.calls::int8 as calls,
  s.total_time::numeric as total_exec_time_ms,
  s.mean_time::numeric as mean_exec_time_ms,
  s.max_time::numeric as max_exec_time_ms,
  null::numeric as total_plan_time_ms,
  s.rows::int8 as rows,
  s.shared_blks_hit::int8 as shared_blks_hit,
  s.shared_blks_read::int8 as shared_blks_read,
  s.shared_blks_dirtied::int8 as shared_blks_dirtied,
  s.shared_blks_written::int8 as shared_blks_written,
  s.temp_blks_read::int8 as temp_blks_read,
  s.temp_blks_written::int8 as temp_blks_written,
  s.blk_read_time::numeric as blk_read_time_ms,
  s.blk_write_time::numeric as blk_write_time_ms,
  null::int8 as wal_records,
  null::int8 as wal_fpi,
  null::numeric as wal_bytes,
  left(coalesce(s.query, '<query text unavailable>'), 4000) as query,
  case when s.queryid is null then 'unknown' else 'ok' end as pg_diag_internal_severity,
  case when s.queryid is null then 'Query ID and SQL text are hidden for this statement owner' else '' end
    as pg_diag_internal_reason
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database()
order by s.total_time desc nulls last
limit 50
