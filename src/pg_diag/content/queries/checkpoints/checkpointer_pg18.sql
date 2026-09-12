select
  current_database() as datname,
  num_timed,
  num_requested,
  num_done,
  -- share of checkpoint triggers that were actually performed (idle checkpoints are skipped)
  (100.0 * num_done / nullif(num_timed + num_requested, 0))
    as performed_share_pct,
  restartpoints_timed,
  restartpoints_req,
  restartpoints_done,
  write_time as write_time_ms,
  sync_time as sync_time_ms,
  buffers_written,
  slru_written,
  stats_reset,
  extract(epoch from pg_catalog.clock_timestamp() - stats_reset)::int8 as stats_age_seconds
from pg_catalog.pg_stat_checkpointer
