with stats_epoch as (
  -- Lower bound of the observation window for cumulative counters: they have accumulated
  -- at least since this moment. pg_stat_database.stats_reset is exact when set (on
  -- PostgreSQL 15+ it stays NULL until pg_stat_reset() is called). A shared statistics
  -- reset after the postmaster started is either a crash recovery, which discards every
  -- counter, or a targeted pg_stat_reset_shared(), which leaves per-object counters older
  -- than it; taking the latest candidate therefore never overstates the window. Statistics
  -- survive clean restarts, so the postmaster start time is a lower bound as well.
  select
    db.stats_reset as stats_reset,
    greatest(pg_catalog.pg_postmaster_start_time(), db.stats_reset, bg.stats_reset) as stats_window_start,
    case
      when db.stats_reset is not null
        and db.stats_reset = greatest(pg_catalog.pg_postmaster_start_time(), db.stats_reset, bg.stats_reset)
        then 'pg_stat_database.stats_reset'
      when bg.stats_reset is not null
        and bg.stats_reset = greatest(pg_catalog.pg_postmaster_start_time(), db.stats_reset, bg.stats_reset)
        then 'shared statistics reset after postmaster start (crash recovery or pg_stat_reset_shared(); per-object counters may be older)'
      else 'postmaster start time (statistics survive clean restarts, so counters may be older)'
    end as stats_window_source
  from pg_catalog.pg_stat_database db
  cross join pg_catalog.pg_stat_bgwriter bg
  where db.datname = pg_catalog.current_database()
)
select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  io.relid,
  schemaname,
  relname,
  e.stats_reset,
  e.stats_window_start,
  e.stats_window_source,
  heap_blks_read::int8 as heap_blks_read,
  heap_blks_hit::int8 as heap_blks_hit,
  idx_blks_read::int8 as idx_blks_read,
  idx_blks_hit::int8 as idx_blks_hit,
  toast_blks_read::int8 as toast_blks_read,
  toast_blks_hit::int8 as toast_blks_hit,
  tidx_blks_read::int8 as tidx_blks_read,
  tidx_blks_hit::int8 as tidx_blks_hit,
  (heap_blks_read + idx_blks_read + toast_blks_read + tidx_blks_read)::int8 as total_blks_read,
  (heap_blks_hit + idx_blks_hit + toast_blks_hit + tidx_blks_hit)::int8 as total_blks_hit,
  (
    (heap_blks_hit + idx_blks_hit + toast_blks_hit + tidx_blks_hit)::numeric * 100.0
    / nullif(heap_blks_hit + idx_blks_hit + toast_blks_hit + tidx_blks_hit + heap_blks_read + idx_blks_read + toast_blks_read + tidx_blks_read, 0)) as cache_hit_pct
from pg_statio_all_tables io
cross join stats_epoch e
where schemaname not in ('pg_catalog', 'information_schema')
  and schemaname !~ '^pg_toast'
order by total_blks_read desc nulls last, schemaname, relname, io.relid
limit 200
