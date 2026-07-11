with io as (
  select
    backend_type,
    object,
    context,
    sum(coalesce(reads, 0))::int8 as reads,
    round(sum(coalesce(reads, 0) * op_bytes)::numeric / 1048576.0, 3) as read_bytes_mb,
    sum(coalesce(read_time, 0))::numeric as read_time_ms,
    sum(coalesce(writes, 0))::int8 as writes,
    round(sum(coalesce(writes, 0) * op_bytes)::numeric / 1048576.0, 3) as write_bytes_mb,
    sum(coalesce(write_time, 0))::numeric as write_time_ms,
    sum(coalesce(writebacks, 0))::int8 as writebacks,
    round(sum(coalesce(writebacks, 0) * op_bytes)::numeric / 1048576.0, 3)
      as writeback_bytes_mb,
    sum(coalesce(writeback_time, 0))::numeric as writeback_time_ms,
    sum(coalesce(fsyncs, 0))::int8 as fsyncs,
    sum(coalesce(fsync_time, 0))::numeric as fsync_time_ms,
    sum(coalesce(extends, 0))::int8 as extends,
    round(sum(coalesce(extends, 0) * op_bytes)::numeric / 1048576.0, 3) as extend_bytes_mb,
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
  read_bytes_mb,
  read_time_ms,
  writes,
  write_bytes_mb,
  write_time_ms,
  writebacks,
  writeback_bytes_mb,
  writeback_time_ms,
  fsyncs,
  fsync_time_ms,
  extends,
  extend_bytes_mb,
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
order by read_bytes_mb desc nulls last, backend_type, object, context
