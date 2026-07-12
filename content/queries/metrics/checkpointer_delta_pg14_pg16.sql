select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  checkpoints_timed::int8 as checkpoints_timed,
  checkpoints_req::int8 as checkpoints_requested,
  (checkpoints_timed + checkpoints_req)::int8 as checkpoints_done,
  null::int8 as restartpoints_timed,
  null::int8 as restartpoints_requested,
  null::int8 as restartpoints_done,
  (checkpoint_write_time::numeric) as write_time_ms,
  (checkpoint_sync_time::numeric) as sync_time_ms,
  buffers_checkpoint::int8 as buffers_written,
  null::int8 as slru_written
from pg_catalog.pg_stat_bgwriter
