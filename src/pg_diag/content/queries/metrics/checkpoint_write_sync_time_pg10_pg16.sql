select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  checkpoint_write_time::numeric as write_time_ms,
  checkpoint_sync_time::numeric as sync_time_ms
from pg_catalog.pg_stat_bgwriter
