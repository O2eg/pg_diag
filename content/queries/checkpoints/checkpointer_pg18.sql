select
  current_database() as datname,
  num_timed,
  num_requested,
  num_done,
  (100.0 * num_done / nullif(num_timed + num_requested, 0))
    as checkpoint_completion_pct,
  restartpoints_timed,
  restartpoints_req,
  restartpoints_done,
  write_time,
  sync_time,
  buffers_written,
  slru_written,
  stats_reset,
  extract(epoch from pg_catalog.clock_timestamp() - stats_reset)::int8 as stats_age_seconds
from pg_catalog.pg_stat_checkpointer
