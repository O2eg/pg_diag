select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset as bgwriter_stats_reset,
  stats_reset as checkpointer_stats_reset,
  stats_reset as io_stats_reset,
  (buffers_checkpoint::numeric * current_setting('block_size')::int8)::int8
    as checkpointer_bytes,
  (buffers_clean::numeric * current_setting('block_size')::int8)::int8
    as bgwriter_bytes,
  (buffers_backend::numeric * current_setting('block_size')::int8)::int8
    as backend_bytes
from pg_catalog.pg_stat_bgwriter
