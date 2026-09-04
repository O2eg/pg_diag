select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset as bgwriter_stats_reset,
  stats_reset as io_stats_reset,
  maxwritten_clean::int8 as bgwriter_stops,
  buffers_backend_fsync::int8 as backend_fsyncs
from pg_catalog.pg_stat_bgwriter
