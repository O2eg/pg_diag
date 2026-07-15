select
  current_database() as datname,
  buffers_clean,
  maxwritten_clean,
  buffers_alloc,
  stats_reset,
  extract(epoch from pg_catalog.clock_timestamp() - stats_reset)::int8 as stats_age_seconds,
  'ok'::text as pg_diag_internal_severity,
  ''::text as pg_diag_internal_reason
from pg_catalog.pg_stat_bgwriter
