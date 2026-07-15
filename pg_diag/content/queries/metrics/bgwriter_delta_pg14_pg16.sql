select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  buffers_clean::int8 as buffers_clean,
  maxwritten_clean::int8 as maxwritten_clean,
  buffers_backend::int8 as buffers_backend,
  buffers_backend_fsync::int8 as buffers_backend_fsync,
  buffers_alloc::int8 as buffers_alloc
from pg_catalog.pg_stat_bgwriter
