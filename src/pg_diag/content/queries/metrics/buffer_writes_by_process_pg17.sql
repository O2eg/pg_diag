select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  bgwriter.stats_reset as bgwriter_stats_reset,
  checkpointer.stats_reset as checkpointer_stats_reset,
  backends.io_stats_reset,
  (checkpointer.buffers_written::numeric * current_setting('block_size')::int8)::int8
    as checkpointer_bytes,
  (bgwriter.buffers_clean::numeric * current_setting('block_size')::int8)::int8
    as bgwriter_bytes,
  backends.backend_bytes
from pg_catalog.pg_stat_bgwriter as bgwriter
cross join pg_catalog.pg_stat_checkpointer as checkpointer
cross join (
  select
    max(stats_reset) as io_stats_reset,
    sum((coalesce(writes, 0) + coalesce(extends, 0)) * op_bytes)::int8
      as backend_bytes
  from pg_catalog.pg_stat_io
  where object = 'relation'
    and backend_type not in ('checkpointer', 'background writer')
) as backends
