select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  num_timed::int8 as checkpoints_timed,
  num_requested::int8 as checkpoints_requested,
  num_done::int8 as checkpoints_done,
  restartpoints_timed::int8 as restartpoints_timed,
  restartpoints_req::int8 as restartpoints_requested,
  restartpoints_done::int8 as restartpoints_done,
  (write_time::numeric) as write_time_ms,
  (sync_time::numeric) as sync_time_ms,
  buffers_written::int8 as buffers_written,
  slru_written::int8 as slru_written
from pg_catalog.pg_stat_checkpointer
