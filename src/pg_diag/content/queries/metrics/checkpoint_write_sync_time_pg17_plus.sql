select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  write_time::numeric as write_time_ms,
  sync_time::numeric as sync_time_ms
from pg_catalog.pg_stat_checkpointer
