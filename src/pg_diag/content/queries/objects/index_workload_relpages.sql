with recursive stats_epoch as (
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
workload_roots as (
  select
    si.relid,
    si.indexrelid,
    si.schemaname,
    si.relname,
    si.indexrelname,
    si.idx_scan,
    si.idx_tup_read,
    si.idx_tup_fetch
  from pg_stat_user_indexes si
  where si.idx_scan <> 0
  order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname, si.indexrelid
  limit 100
),
candidate_indexes as (
  select wr.*
  from workload_roots wr
  join pg_class c on c.oid = wr.indexrelid
  where c.relkind in ('i', 'I')
),
index_tree as (
  select ci.indexrelid as root_oid, ci.indexrelid as index_oid
  from candidate_indexes ci
  union
  select it.root_oid, i.inhrelid
  from index_tree it
  join pg_inherits i on i.inhparent = it.index_oid
),
bounded_index_tree as (
  select *
  from index_tree
  limit 3001
),
limited_index_tree as (
  select *
  from bounded_index_tree
  limit 3000
),
tree_coverage as (
  select (count(*) > 3000) as tree_truncated
  from bounded_index_tree
),
page_estimates as (
  select
    it.root_oid,
    coalesce(
      sum(greatest(coalesce(c.relpages, 0), 0))
        filter (where c.relkind = 'i'),
      0
    )::int8 as estimated_index_relpages
  from limited_index_tree it
  join pg_class c on c.oid = it.index_oid
  group by it.root_oid
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
  pe.estimated_index_relpages,
  (
    pe.estimated_index_relpages
    * current_setting('block_size')::int8
  )::int8 as estimated_index_size_bytes,
  tc.tree_truncated
from candidate_indexes si
join page_estimates pe on pe.root_oid = si.indexrelid
cross join tree_coverage tc
left join pg_statio_all_indexes io on io.indexrelid = si.indexrelid
cross join stats_epoch e
order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname, si.indexrelid
