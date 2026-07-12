with database_stats as (
select
  statement_timestamp() as snapshot_time,
  datid,
  datname,
  stats_reset,
  numbackends,
  xact_commit,
  xact_rollback,
  blks_read,
  blks_hit,
  tup_returned,
  tup_fetched,
  tup_inserted,
  tup_updated,
  tup_deleted,
  conflicts,
  temp_files,
  temp_bytes,
  deadlocks,
  blk_read_time,
  blk_write_time,
  extract(epoch from (now() - pg_postmaster_start_time()))::int8 as postmaster_uptime_s,
  case when pg_is_in_recovery() then 1 else 0 end as in_recovery_int
from pg_stat_database
where datname is not null
)
select
  database_stats.*,
  case
    when deadlocks > 0 then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  concat_ws(
    '; ',
    case when deadlocks > 0 then deadlocks::text || ' cumulative deadlock(s) detected' end
  ) as pg_diag_internal_reason
from database_stats
