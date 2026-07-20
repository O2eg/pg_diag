select
  current_database() as datname,
  checkpoints_timed,
  checkpoints_req,
  (checkpoints_timed + checkpoints_req)::int8 as checkpoints_total,
  (
    100.0 * checkpoints_req / nullif(checkpoints_timed + checkpoints_req, 0)) as requested_checkpoint_pct,
  checkpoint_write_time,
  checkpoint_sync_time,
  buffers_checkpoint,
  buffers_clean,
  maxwritten_clean,
  buffers_backend,
  buffers_backend_fsync,
  buffers_alloc,
  stats_reset,
  extract(epoch from pg_catalog.clock_timestamp() - stats_reset)::int8 as stats_age_seconds,
  case when buffers_backend_fsync > 0 then 'medium' else 'ok' end
    as pg_diag_internal_severity,
  case
    when buffers_backend_fsync > 0 then 'client backends performed their own fsyncs since reset'
    else ''
  end as pg_diag_internal_reason
from pg_catalog.pg_stat_bgwriter
