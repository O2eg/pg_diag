select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  buffers_alloc::int8 as buffers_alloc,
  buffers_clean::int8 as buffers_clean
from pg_catalog.pg_stat_bgwriter
