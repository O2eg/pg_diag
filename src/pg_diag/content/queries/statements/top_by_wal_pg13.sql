select
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.dbid,
  s.userid,
  null::boolean as toplevel,
  s.queryid::text as query_id,
  case when s.queryid is null then 'statistics_only' else 'full' end as identity_visibility,
  s.calls::int8 as calls,
  s.wal_bytes::numeric as wal_bytes,
  s.wal_records::int8 as wal_records,
  s.wal_fpi::int8 as wal_fpi,
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
order by s.wal_bytes desc nulls last
limit 50
