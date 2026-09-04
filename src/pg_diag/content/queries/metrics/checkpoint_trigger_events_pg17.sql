select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  num_timed::int8 as checkpoints_timed,
  num_requested::int8 as checkpoints_requested,
  null::int8 as checkpoints_completed
from pg_catalog.pg_stat_checkpointer
