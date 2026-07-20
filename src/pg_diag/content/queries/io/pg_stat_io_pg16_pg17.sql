with io as (
  select
    backend_type,
    object,
    context,
    sum(coalesce(reads, 0))::int8 as reads,
    sum(coalesce(reads, 0) * op_bytes)::numeric as read_bytes,
    sum(coalesce(read_time, 0))::numeric as read_time_ms,
    sum(coalesce(writes, 0))::int8 as writes,
    sum(coalesce(writes, 0) * op_bytes)::numeric as write_bytes,
    sum(coalesce(write_time, 0))::numeric as write_time_ms,
    sum(coalesce(writebacks, 0))::int8 as writebacks,
    sum(coalesce(writebacks, 0) * op_bytes)::numeric as writeback_bytes,
    sum(coalesce(writeback_time, 0))::numeric as writeback_time_ms,
    sum(coalesce(fsyncs, 0))::int8 as fsyncs,
    sum(coalesce(fsync_time, 0))::numeric as fsync_time_ms,
    sum(coalesce(extends, 0))::int8 as extends,
    sum(coalesce(extends, 0) * op_bytes)::numeric as extend_bytes,
    sum(coalesce(hits, 0))::int8 as hits,
    sum(coalesce(evictions, 0))::int8 as evictions,
    sum(coalesce(reuses, 0))::int8 as reuses,
    max(stats_reset) as stats_reset
  from pg_catalog.pg_stat_io
  group by backend_type, object, context
)
select
  current_database() as datname,
  backend_type,
  object,
  context,
  reads,
  read_bytes,
  read_time_ms,
  writes,
  write_bytes,
  write_time_ms,
  writebacks,
  writeback_bytes,
  writeback_time_ms,
  fsyncs,
  fsync_time_ms,
  extends,
  extend_bytes,
  hits,
  evictions,
  reuses,
  current_setting('track_io_timing')::boolean as track_io_timing,
  current_setting('track_wal_io_timing')::boolean as track_wal_io_timing,
  stats_reset,
  extract(epoch from pg_catalog.clock_timestamp() - stats_reset)::int8 as stats_age_seconds,
  case
    when backend_type = 'client backend' and object = 'relation' and fsyncs > 0
      then 'medium'
    else 'ok'
  end
    as pg_diag_internal_severity,
  case
    when backend_type = 'client backend' and object = 'relation' and fsyncs > 0
      then 'client backends performed fsyncs since I/O statistics were reset'
    else ''
  end as pg_diag_internal_reason
from io
order by read_bytes desc nulls last, backend_type, object, context
