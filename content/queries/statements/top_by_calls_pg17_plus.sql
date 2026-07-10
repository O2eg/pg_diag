select
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.dbid,
  s.userid,
  s.toplevel,
  s.queryid::text as query_id,
  case when s.queryid is null then 'statistics_only' else 'full' end as identity_visibility,
  s.calls::int8 as calls,
  round(s.total_exec_time::numeric, 3) as total_exec_time_ms,
  round(s.mean_exec_time::numeric, 3) as mean_exec_time_ms,
  s.rows::int8 as rows,
  s.shared_blks_hit::int8 as shared_blks_hit,
  s.shared_blks_read::int8 as shared_blks_read,
  s.wal_bytes::numeric as wal_bytes,
  s.stats_since,
  left(coalesce(s.query, '<query text unavailable>'), 4000) as query,
  case when s.queryid is null then 'unknown' else 'ok' end as pg_diag_internal_severity,
  case
    when s.queryid is null then 'Query ID and SQL text are hidden for this statement owner'
    else ''
  end as pg_diag_internal_reason
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database()
order by s.calls desc nulls last
limit 50
