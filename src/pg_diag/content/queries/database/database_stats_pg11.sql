with database_stats as (
select
  statement_timestamp() as snapshot_time,
  datid,
  datname,
  stats_reset,
  -- lower bound of the counter window: counters have accumulated at least since this moment
  -- (crash recovery discards them without setting stats_reset; a targeted shared reset leaves
  -- them older; statistics survive clean restarts)
  greatest(pg_postmaster_start_time(), stats_reset, (select stats_reset from pg_catalog.pg_stat_bgwriter)) as stats_window_start,
  case
    when stats_reset is not null
      and stats_reset = greatest(pg_postmaster_start_time(), stats_reset, (select stats_reset from pg_catalog.pg_stat_bgwriter))
      then 'pg_stat_database.stats_reset'
    when (select stats_reset from pg_catalog.pg_stat_bgwriter) > pg_postmaster_start_time()
      then 'shared statistics reset after postmaster start (crash recovery or pg_stat_reset_shared(); counters may be older)'
    else 'postmaster start time (statistics survive clean restarts, so counters may be older)'
  end as stats_window_source,
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
  pg_is_in_recovery() as in_recovery
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
