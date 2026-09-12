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
candidates as (
  select
    i.indrelid,
    i.indexrelid,
    n.nspname as schemaname,
    tbl.relname as table_name,
    idx.relname as index_name,
    tbl.relpages as table_relpages,
    idx.relpages as index_relpages,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch
  from pg_index i
  join pg_class idx on idx.oid = i.indexrelid and idx.relkind = 'i'
  join pg_class tbl on tbl.oid = i.indrelid and tbl.relkind = 'r'
  join pg_namespace n on n.oid = idx.relnamespace
  left join pg_stat_user_indexes s on s.indexrelid = idx.oid
  where n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
    and tbl.relpages > 0
    and tbl.relpages::int8 * current_setting('block_size')::int8 >= 1024 * 1024
    and idx.relpages::numeric / tbl.relpages > 0.5
  order by idx.relpages::numeric / nullif(tbl.relpages, 0) desc,
           idx.relpages desc, n.nspname, tbl.relname, idx.relname, i.indexrelid
  limit 100
),
sized_candidates as (
  select
    c.*,
    pg_relation_size(c.indrelid)::int8 as table_size_bytes,
    pg_relation_size(c.indexrelid)::int8 as index_size_bytes
  from candidates c
)
select
  c.indrelid as table_oid,
  c.indexrelid as index_oid,
  c.schemaname,
  c.table_name,
  c.index_name,
  e.stats_reset,
  e.stats_window_start,
  e.stats_window_source,
  c.table_size_bytes,
  c.index_size_bytes,
  (c.index_size_bytes::numeric * 100 / nullif(c.table_size_bytes, 0)) as index_to_table_pct,
  c.idx_scan,
  c.idx_tup_read,
  c.idx_tup_fetch
from sized_candidates c
cross join stats_epoch e
where c.table_size_bytes >= 1024 * 1024
order by index_to_table_pct desc nulls last, index_size_bytes desc, c.indexrelid
