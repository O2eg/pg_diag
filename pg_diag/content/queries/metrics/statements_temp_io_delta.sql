select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.dbid,
  s.userid,
  s.toplevel,
  (select stats_reset from pg_stat_statements_info) as global_stats_reset,
  s.queryid::text as query_id,
  s.temp_blks_read::int8 as temp_blks_read,
  s.temp_blks_written::int8 as temp_blks_written,
  ((s.temp_blks_read + s.temp_blks_written)::numeric * current_setting('block_size')::int)
    as temp_io_bytes,
  (s.temp_blk_read_time::numeric) as temp_read_time_ms,
  (s.temp_blk_write_time::numeric) as temp_write_time_ms,
  ''::text as query
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database() and s.queryid is not null
order by (s.temp_blks_read + s.temp_blks_written) desc nulls last
limit 50
