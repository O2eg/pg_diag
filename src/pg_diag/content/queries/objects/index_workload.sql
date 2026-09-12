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
),
candidate_indexes as (
  select
    si.relid,
    si.indexrelid,
    si.schemaname,
    si.relname,
    si.indexrelname,
    si.idx_scan,
    si.idx_tup_read,
    si.idx_tup_fetch,
    c.relpages
  from pg_stat_all_indexes si
  join pg_class c on c.oid = si.indexrelid
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname !~ '^pg_toast'
    and si.idx_scan <> 0
  order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname, si.indexrelid
  limit 100
)
select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  si.relid,
  si.indexrelid,
  si.schemaname,
  si.relname,
  si.indexrelname,
  e.stats_reset,
  e.stats_window_start,
  e.stats_window_source,
  si.idx_scan::int8 as idx_scan,
  si.idx_tup_read::int8 as idx_tup_read,
  si.idx_tup_fetch::int8 as idx_tup_fetch,
  coalesce(io.idx_blks_read, 0)::int8 as idx_blks_read,
  coalesce(io.idx_blks_hit, 0)::int8 as idx_blks_hit,
  pg_relation_size(si.indexrelid)::int8 as index_size_bytes,
  si.relpages::int8 as index_relpages
from candidate_indexes si
left join pg_statio_all_indexes io on io.indexrelid = si.indexrelid
cross join stats_epoch e
order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname, si.indexrelid
