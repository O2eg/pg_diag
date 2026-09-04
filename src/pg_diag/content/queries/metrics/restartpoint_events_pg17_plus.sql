select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  restartpoints_timed::int8 as restartpoints_timed,
  restartpoints_req::int8 as restartpoints_requested,
  restartpoints_done::int8 as restartpoints_done
from pg_catalog.pg_stat_checkpointer
