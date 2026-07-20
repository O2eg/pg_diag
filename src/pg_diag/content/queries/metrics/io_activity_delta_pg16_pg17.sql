select
  statement_timestamp() as snapshot_time,
  backend_type,
  object,
  context,
  stats_reset,
  reads::int8 as reads,
  (reads::numeric * op_bytes) as read_bytes,
  read_time::numeric as read_time_ms,
  writes::int8 as writes,
  (writes::numeric * op_bytes) as write_bytes,
  write_time::numeric as write_time_ms,
  writebacks::int8 as writebacks,
  writeback_time::numeric as writeback_time_ms,
  extends::int8 as extends,
  (extends::numeric * op_bytes) as extend_bytes,
  extend_time::numeric as extend_time_ms,
  fsyncs::int8 as fsyncs,
  fsync_time::numeric as fsync_time_ms,
  hits::int8 as hits,
  evictions::int8 as evictions,
  reuses::int8 as reuses,
  case
    when num_nonnulls(reads, writes, extends) = 0 then null
    else ((coalesce(reads, 0) + coalesce(writes, 0) + coalesce(extends, 0))::numeric * op_bytes)
  end as total_bytes
from pg_catalog.pg_stat_io
order by total_bytes desc nulls last, backend_type, object, context
