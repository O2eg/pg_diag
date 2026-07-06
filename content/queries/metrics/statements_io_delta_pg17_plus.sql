select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.queryid::text as query_id,
  s.shared_blks_read::int8 as shared_blks_read,
  s.shared_blks_written::int8 as shared_blks_written,
  round(s.shared_blk_read_time::numeric, 3) as blk_read_time_ms,
  round(s.shared_blk_write_time::numeric, 3) as blk_write_time_ms,
  left(coalesce(s.query, '<query text unavailable>'), 4000) as query
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database()
order by s.shared_blks_read desc nulls last
limit 50
