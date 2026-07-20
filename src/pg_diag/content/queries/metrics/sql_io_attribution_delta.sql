select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, k.userid::text) as rolname,
  k.dbid,
  k.userid,
  k.top as toplevel,
  k.stats_since as kcache_stats_since,
  k.queryid::text as query_id,
  s.calls::int8 as calls,
  k.exec_reads::int8 as exec_reads,
  k.exec_writes::int8 as exec_writes,
  (k.exec_reads + k.exec_writes)::int8 as exec_io_bytes,
  (
    (s.shared_blks_read + s.local_blks_read + s.temp_blks_read)::numeric
    * current_setting('block_size')::int
  ) as pg_read_bytes,
  (
    (s.shared_blks_written + s.local_blks_written + s.temp_blks_written)::numeric
    * current_setting('block_size')::int
  ) as pg_write_bytes,
  (
    (
      s.shared_blks_read + s.local_blks_read + s.temp_blks_read
      + s.shared_blks_written + s.local_blks_written + s.temp_blks_written
    )::numeric * current_setting('block_size')::int
  ) as pg_io_bytes,
  s.query as query
from pg_stat_kcache() k
join pg_stat_statements s
  on s.dbid = k.dbid and s.userid = k.userid and s.queryid = k.queryid
join pg_database d on d.oid = k.dbid
left join pg_roles r on r.oid = k.userid
where d.datname = current_database() and k.top is true
order by (k.exec_reads + k.exec_writes) desc nulls last
limit 250
