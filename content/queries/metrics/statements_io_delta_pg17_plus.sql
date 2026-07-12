select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.dbid,
  s.userid,
  s.toplevel,
  (select stats_reset from pg_stat_statements_info) as global_stats_reset,
  s.stats_since as entry_stats_since,
  s.queryid::text as query_id,
  s.shared_blks_read::int8 as shared_blks_read,
  s.shared_blks_written::int8 as shared_blks_written,
  (s.shared_blk_read_time::numeric) as blk_read_time_ms,
  (s.shared_blk_write_time::numeric) as blk_write_time_ms,
  ''::text as query
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database() and s.queryid is not null
order by s.shared_blks_read desc nulls last
limit 50
